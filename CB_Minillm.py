import tiktoken
import numpy as np
import tensorflow as tf
from tensorflow import keras
import matplotlib.pyplot as plt
import os
import mlflow
import argparse


mlflow.start_run()

parser = argparse.ArgumentParser()  ## to read arguments from command line, we will pass train data and output dir for model (in job command)
parser.add_argument("--train_data", type=str, required=True, help="Path to training data file")
parser.add_argument("--output_dir", type=str, default="./outputs") 
args = parser.parse_args()

os.makedirs(args.output_dir, exist_ok=True)

ALL_TOKENS = 100277 #GPT4
CHUNK_BLOCK_SIZE = 128  # number of tokens in each training example
CHUNK_TRAIN_SPLIT = 0.8
EMBEDDING_SIZE = 128 # size of the token embeddings and transformer model =CHUNK_BLOCK_SIZE
BATCH_SIZE = 32
TXT_FOLDER = './TEXT_data_engineering'
NORMALIZED_TRAIN_FILE = 'final_train_data_normalized.txt'
ATTENTION_HEADS = 4
TRANSFORMER_BLOCKS = 4
DROPOUT = 0.1
EPOCHS = 10
LEARNING_RATE = 3e-4

mlflow.log_params({
    "block_size": CHUNK_BLOCK_SIZE,
    "embedding_size": EMBEDDING_SIZE,
    "attention_heads": ATTENTION_HEADS,
    "transformer_blocks": TRANSFORMER_BLOCKS,
    "dropout": DROPOUT,
    "batch_size": BATCH_SIZE,
    "learning_rate": LEARNING_RATE,
    "epochs": EPOCHS,
})

def tokenize_bpe4(text):
    
    bpe4 = tiktoken.get_encoding("cl100k_base")  # Get the BPE encoding for GPT-4
    
    encode = lambda e: bpe4.encode(e, allowed_special={"<|endoftext|>"})  # Function to encode text to BPE tokens, allowing special tokens like  end-of-text token 

    decode = lambda d: bpe4.decode(d)  # Function to decode BPE tokens back to text
    
    sample_bpe4 = encode(text[:300])
    
    return {
        "name": "bpe4",
        "vocab_size": bpe4.n_vocab,
        "encode": encode,
        "decode": decode,
        "sample": [bpe4.decode([i]) for i in sample_bpe4[:30]]
    }


txt_file = args.train_data   # f"{TXT_FOLDER}/{NORMALIZED_TRAIN_FILE}"   changed for AZURE
with open(txt_file, 'r', encoding='utf-8') as f:
    text = f.read()

toke_dic = tokenize_bpe4(text)

print(f"Nb of tokens in vocabulary: {toke_dic['vocab_size']:,}")
print(f"Example             : {toke_dic['sample'][:10]}")

def chunking(toke_dic, text, block_size=CHUNK_BLOCK_SIZE, train_split=CHUNK_TRAIN_SPLIT, batch_size=BATCH_SIZE):
    
    encode = toke_dic["encode"]
    
    all_tokens = encode(text)  # number of tokens its the same as number of characters
    print(f"Total tokens: {len(all_tokens)}")
    mlflow.log_metric("total_tokens", len(all_tokens))
    
    data = np.array(all_tokens, dtype=np.int32)  # Convert the list of tokens into a NumPy array of type int32 for efficient processing
    split = int(len(data) * train_split)  # Calculate the index for splitting the data into training and validation sets
    
    train = data[:split]  # Get the training data
    val = data[split:]    # Get the validation data
    
    """ We prepared Train and Validate datasets"""
    
    def make_pairs_of_tokens(data):
        x, y = [], []
        for i in range(len(data) - block_size):  # 
            x.append(data[i:i+block_size])  # Append a sequence of tokens of length block_size to x
            y.append(data[i+1:i+1+block_size])  # Append the next sequence of tokens (shifted by one) to y
        return np.array(x), np.array(y)  # Convert the lists of input and target sequences into NumPy arrays
    
    x_train, y_train = make_pairs_of_tokens(train)  # Create input-target pairs for the training data
    x_val, y_val = make_pairs_of_tokens(val)        # Create input-target pairs for the validation data
    
    # tf.data.Dataset — Automatically handles batching, shuffling, and prefetching of data for efficient training
    ds_train = (
        tf.data.Dataset     
        .from_tensor_slices((x_train, y_train))
        .shuffle(10_000)          # randomly shuffle order of chunks
        .batch(batch_size)        # group batches
        .prefetch(tf.data.AUTOTUNE)  # preload data while the model is training to improve performance
    )

    ds_val = (
        tf.data.Dataset
        .from_tensor_slices((x_val, y_val))
        .batch(batch_size)
        .prefetch(tf.data.AUTOTUNE)
    )

    return ds_train, ds_val

ds_train, ds_val = chunking(toke_dic, text)


for x_batch, y_batch in ds_train.take(1):
    print(f"\nx batch: {x_batch.shape}  (batch_size, block_size)")
    print(f"y batch: {y_batch.shape}  (batch_size, block_size)")
    print(f"Excample x[0]: {x_batch[0].numpy()[:8]} ...")
    print(f"Example y[0]: {y_batch[0].numpy()[:8]} ...")
    
def transformer(x, embedd_size=EMBEDDING_SIZE, attn_heads=ATTENTION_HEADS, dropout=DROPOUT):
    savedX = x  # Save the input to add it back later 
    #attention
    x = keras.layers.LayerNormalization(epsilon=1e-6)(x)  # Normalize the input to stabilize and speed up training
    x = keras.layers.MultiHeadAttention(
        num_heads=attn_heads, 
        key_dim=embedd_size//attn_heads, # we divide it because in paraller attention head will learn different relation between tokens like one meaning, second grammar...
        dropout=dropout,
        use_bias=False
    )(x, x, use_causal_mask=True)  # Apply multi-head self-attention with a causal mask to prevent attending to future tokens if False tocken on position 3 can see tokens on positions 7,8 etc, so no prediction and learning
    # x, x means that the same input is used for queries, keys, and values in the attention mechanism
    x = keras.layers.Dropout(dropout)(x)  # Apply dropout for regularization
    
    x = x + savedX  # Add the original input back to the output of the attention layer (residual connection)
    
    #feed forward
    savedX = x  # Save the output of the attention layer to add it back later
    x = keras.layers.LayerNormalization(epsilon=1e-6)(x)  # Normalize the output of the attention layer
    x = keras.layers.Dense(4 * embedd_size, activation="gelu")(x) # 4 because in the original transformer architecture, the feed-forward network has an inner layer that is typically 4 times larger than the embedding size to learn better and give capasity to learn
    x = keras.layers.Dense(embedd_size)(x)  # Apply a feed-forward neural network with one hidden layer
    x = keras.layers.Dropout(dropout)(x)
    
    x = x + savedX # this is required to have backpropagation to work properly. Without gradients may disappear and model will not learn -- to reed more
    
    return x


def modelMiniLLM(block_size=CHUNK_BLOCK_SIZE, 
                 vocab_size=ALL_TOKENS, 
                 embedd_size=EMBEDDING_SIZE, 
                 transformer_blocks=TRANSFORMER_BLOCKS, 
                 attn_heads=ATTENTION_HEADS, 
                 dropout=DROPOUT):
    
    inputs = keras.layers.Input(shape=(block_size,), dtype=tf.int32) 
    x = keras.layers.Embedding(
        input_dim=vocab_size,  # size of the vocabulary (number of unique tokens)
        output_dim=embedd_size  # size of the embedding vectors for each token
    )(inputs)
    
    positions = tf.range( #position for embedding
        start=0,
        limit=block_size, # number of tokens in each training example
        delta=1 # step size for the range of positions
    )
    position_embedding = keras.layers.Embedding(
        input_dim=block_size,  # maximum number of positions (tokens) in the input sequence
        output_dim=embedd_size # size of wectors (the same as in embedding)
    )(positions)
    
    x = x + position_embedding
    
    x = keras.layers.Dropout(dropout)(x)
    
    #Transformer 
    for i in range(transformer_blocks):
        x = transformer(x, embedd_size, attn_heads, dropout)
    
    x = keras.layers.LayerNormalization(epsilon=1e-6)(x)
    
    outputs = keras.layers.Dense(vocab_size, use_bias=False)(x)  # Final output layer that predicts the next token in the sequence for each position

    model = keras.Model(inputs=inputs, outputs=outputs)
    
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=LEARNING_RATE),
        loss=keras.losses.SparseCategoricalCrossentropy(from_logits=True),  # to read
    )
    
    return model

strategy = tf.distribute.get_strategy()
with strategy.scope():
    model = modelMiniLLM()
model.summary()

class MlflowCallback(keras.callbacks.Callback):
    def on_epoch_end(self, epoch, logs=None):
        if logs:
            mlflow.log_metric("train_loss", logs.get("loss"), step=epoch)
            mlflow.log_metric("val_loss", logs.get("val_loss"), step=epoch)
            mlflow.log_metric("learning_rate",
                              float(self.model.optimizer.learning_rate),
                              step=epoch)
    
checkpoint = keras.callbacks.ModelCheckpoint(
    filepath=os.path.join(args.output_dir, "minillm_best.keras"), # save
    monitor="val_loss",             # val loss show how well the model is doing on unseen data 
    save_best_only=True,            # save only if better than previous best
    verbose=1,
)


early_stop = keras.callbacks.EarlyStopping(
    monitor="val_loss",
    patience=3,        # how many epochs wait without improvement before stopping
    restore_best_weights=True,  # come back to the best weights after stopping
    verbose=1,
)

reduce_lr = keras.callbacks.ReduceLROnPlateau( # reduse learning rate when val_loss "stuck"
    monitor="val_loss",
    factor=0.5,        # new lr = lr * 0.5
    patience=2,        # how many epochs wait without improvement before reducing the learning rate
    min_lr=1e-6,       # minimum learning rate to reduce to
    verbose=1,
)

history = model.fit(
    ds_train,
    validation_data=ds_val,
    epochs=EPOCHS,
    callbacks=[checkpoint, early_stop, reduce_lr, MlflowCallback()],
)

# history.history to słownik: {"loss": [...], "val_loss": [...]}
print("\nLLast train Loos:", history.history["loss"][-1])
print("Last val loss  :", history.history["val_loss"][-1])

mlflow.log_metric("final_train_loss", history.history["loss"][-1])
mlflow.log_metric("final_val_loss", history.history["val_loss"][-1])
mlflow.log_metric("epochs_trained", len(history.history["loss"]))

model.save(os.path.join(args.output_dir, "minillm_final.keras"))  
mlflow.tensorflow.log_model(model, "model")

mlflow.end_run()