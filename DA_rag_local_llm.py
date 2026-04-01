import re
import sys
import time
import ollama
import chromadb
import gradio as gr
from pathlib import Path
import argparse
from chromadb import Documents, EmbeddingFunction, Embeddings
import json
import time

KNOWLEDGE_BASE_DIR = "./TEXT_medic_trials/seperated_texts/"
BIELIK_MODEL        = "SpeakLeash/bielik-7b-instruct-v0.1-gguf"
# SpeakLeash/bielik-7b-instruct-v0.1-gguf
# SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M
#speakleash/bielik-11b-v2.3-instruct:Q4_K_M       --- działa super ale wolny
#speakleash/bielik-11b-v2.3-instruct-imatrix:IQ3_XXS   -- zapętla się przy generowaniu odpowiedzi, prawdopodobnie z powodu zbyt dużej ilości informacji w kontekście, który jest dostarczany do modelu. Model może mieć trudności z przetworzeniem tak dużej ilości danych, co prowadzi do nieskończonej pętli generowania odpowiedzi.

EMBED_MODEL         = "mxbai-embed-large"
CHROMA_PATH         = "./chroma_db"
CHROMA_COLLECTION   = "medical_kb"
CHUNK_SIZE          = 800 
CHUNK_OVERLAP       = 3 
TOP_K               = 4
HISTORY_FILE        = "./history.json"

SYSTEM_PROMPT = """Jesteś medycznym asystentem pomagającym pacjentom i ich rodzinom 
zrozumieć wyniki badań medycznych a w szczególności wyniki badań krwi i opisy badań.

Zasady:
- Odpowiadaj wyłącznie po polsku
- Bazuj na informacjach zawartych w kontekście, który ci dostarczam, w przypadku braku napisz odpowiednio "Nie mam wystarczających informacji w bazie RAG" i odpowiedz na pytanie ogólnie zaznaczając że "Odpowiedź z ogólnej wiedzy internetowej:"
- Używaj prostego języka zrozumiałego dla pacjenta, opisuj skomplikowane terminy medycznew prostszy sposób
- Gdy używasz terminu medycznego, wyjaśnij go w nawiasie
- Jeśli pytanie dotyczy leczenia, zawsze dodaj: "Skonsultuj się z lekarzem przed podjęciem decyzji"
- Jeżeli znajdziesz kilka takich samych informacji nie powielaj ich. 
- Jeżeli masz wylistować coś także nie powtarzaj punktów.
- Dane z tabeli pokazuj tylko te które są adekwatne do pytania
- Podawaj źródła jeżeli je znasz
"""

class OllamaEmbedding(EmbeddingFunction):
    def __init__(self):
        pass
    
    def __call__(self, input: Documents) -> Embeddings:

        truncated = [text[:500] for text in input]
        response = ollama.embed(model=EMBED_MODEL, input=truncated)
        return response['embeddings']

def sentences_split(text):
    
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return sentences
    

def load_and_chunk(dirpath: str, max_chars=CHUNK_SIZE, overlap_sents=CHUNK_OVERLAP) -> list:
    chunks = []
    chunk_id = 0
    
    for filepath in Path(dirpath).glob("*.txt"):
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()
        
        sentences = sentences_split(text)
        current_sents, current_chars = [], 0

        for sent in sentences:
            sent_len = len(sent)
            if current_chars + sent_len > max_chars and current_sents:
                chunk_text = " ".join(current_sents)
                chunks.append({
                    "id":       f"chunk_{chunk_id}",
                    "text":     chunk_text,
                    "metadata": {
                        "source":   filepath.name,  
                        "chunk_id": chunk_id,
                        "char_len": len(chunk_text)
                    }
                })
                chunk_id += 1
                current_sents = current_sents[-overlap_sents:] if overlap_sents else []
                current_chars = sum(len(s) for s in current_sents)
            
            current_sents.append(sent)
            current_chars += sent_len

        if current_sents:
            chunk_text = " ".join(current_sents)
            chunks.append({
                "id":       f"chunk_{chunk_id}",
                "text":     chunk_text,
                "metadata": {
                    "source":   filepath.name,
                    "chunk_id": chunk_id,
                    "char_len": len(chunk_text)
                }
            })
            chunk_id += 1
            
    return chunks


def chroma_vector(chunks, force_rebuild=False) -> chromadb.Collection:
    
    client = chromadb.PersistentClient(path = CHROMA_PATH)
    embedding_fn = OllamaEmbedding()
    
    if force_rebuild:
        try:
            client.delete_collection(CHROMA_COLLECTION)
            print("Stara kolekcja usunięta.")
        except:
            pass
    
    collection = client.get_or_create_collection(  # Create or get the Chroma collection it's where the chunks and their embeddings will be stored
        name = CHROMA_COLLECTION,
        embedding_function=embedding_fn,
        metadata={"description": "Medical knowledge base for RAG system"}
    )
    
    if collection.count() >0:
        print(f"Collection '{CHROMA_COLLECTION}' already has {collection.count()} entries. Skipping embedding.")
        return collection
    
    BATCH = 15
    for i in range(0, len(chunks), BATCH):  # i is from 0 to chunk lenght and increases by batch size
        batch = chunks[i:   i + BATCH]
        collection.add(
            ids = [chunk["id"] for chunk in batch],  # unique identifiers for each chunk, used to reference them in the collection
            documents = [chunk["text"] for chunk in batch], # the actual text content of each chunk, which will be stored in the collection and used for retrieval
            metadatas = [chunk["metadata"] for chunk in batch] # additional information about each chunk, such as its source and chunk ID, which can be useful for filtering and understanding the context of retrieved chunks
        )
        print(f"  [{min(i + BATCH, len(chunks))}/{len(chunks)}]")
    print(f"Nb of chunks: {collection.count()}")
    return collection

## RAG PART ###

def retrieve(query, collection: chromadb.Collection, top_k = TOP_K, debug=False): # this function takes a user query and retrieves the most relevant chunks from the Chroma collection based on the query's embedding. It uses the collection's query method to find the top_k most relevant documents (chunks) that match the query.
    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        include=["documents", "distances", "metadatas"]
    )
    documents = results['documents'][0]  # Return the retrieved documents for the first query
    distances = results['distances'][0]   # cosine distance: lower = more similar
    metadatas = results['metadatas'][0]
    
    scored_chunks = [(doc, round(1 - dist, 3), meta)
              for doc, dist, meta in zip(documents, distances, metadatas)] # create a list of tuples where each tuple contains the retrieved document (chunk), its similarity score (calculated as 1 - distance), and its metadata. The similarity score is rounded to three decimal places for easier interpretation.
    if debug:
        print(f"DEBUG — Top {top_k} chunks retrieved for: '{query}'")
        for i, (doc, score, meta) in enumerate(scored_chunks):
            print(f"\n[Chunk {i+1}] Score: {score:.3f} | Source: {meta.get('source')} | chars: {meta.get('char_len')}")
            # Show first 200 chars of each chunk
            preview = doc[:200] + "..." if len(doc) > 200 else doc
            print(preview)

    # Return just the text for the answer generator
    return [(doc, meta.get('source', 'nieznane')) for doc, score, meta in scored_chunks]

def generate_answer(query, context_chunks, history):
    t3 = time.time()
    
    context = "\n\n".join(
        f"[Źródło: {src}]\n{doc}" 
        for doc, src in context_chunks
    )  # Combine the retrieved chunks into a single context string, separated by double newlines for clarity.
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] 
    
    for human_message, rag_message in history[-3:]:
        messages.append({"role": "user", "content": human_message})
        messages.append({"role": "assistant", "content": rag_message})
    
    messages.append({
        "role": "user",
        "content":(
            f"Kontekst medyczny z bazy wiedzy:\n{context}\n\n"
            f"---\n\nPytanie: {query}"
        )
    })   
    t4 = time.time()
    print(f"⏱ Prepare messages: {t4-t3:.2f}s")
    
    response = ollama.chat(
        model=BIELIK_MODEL, 
        messages=messages,
        options={
            "temperature": 0.2, # lower will give answers more fact-based
            "num_predict": 1024, # max tokens in the response
        }
        )  # Generate a response from the Bielik model using the constructed messages, which include the system prompt, conversation history, and the current query with context.
    
    t5 = time.time()
    print(f"⏱ LLM response time: {t5-t4:.2f}s")
    
    return response["message"]["content"]

def load_history():
    if Path(HISTORY_FILE).exists():
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def main():
    
    COMMANDS = {"q", "exit", "quit", "e", "end", "clear", "cls", "debug"}
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--knowledge_base_dir", "-k", type=str, help="Path to the knowledge base file",
        default=KNOWLEDGE_BASE_DIR
    )
    parser.add_argument("--debug", "-d", action="store_true", help="Show first 200 characters from top k chunks")
    parser.add_argument("--rebuild", "-r", action="store_true", help="Przebuduj kolekcję od nowa")

    args = parser.parse_args()
    
    if not Path(args.knowledge_base_dir).exists():
        print(f"Brak wsadu dla RAGa: {args.knowledge_base_dir}")
        sys.exit(1)
        
    #check if ollama is running
    try: 
        ollama.list()
    except Exception:
        print("Ollama nie pracuje, Uruchom")
        sys.exit(1)
    
    
    #Build the knowledge base
    chunks = load_and_chunk(args.knowledge_base_dir)
    # DIAGNOSTYKA
    print(f"\nKatalog (pełna ścieżka): {Path(args.knowledge_base_dir).resolve()}")
    print(f"Liczba chunków: {len(chunks)}")
    if chunks:
        print("Pierwsze 5 źródeł:")
        for c in chunks[:5]:
            print(f"  {c['metadata']['source']}")
    else:
        print("BRAK CHUNKÓW — folder pusty lub zła ścieżka!")
    
    collection = chroma_vector(chunks, force_rebuild=args.rebuild)
    
    debug_mode = args.debug
    print("System gotowy. Możesz zadawać pytania. By zakończyć wpisz 'q', 'exit' lub 'quit', by wyczyścić historię wpisz 'clear' lub 'cls'.")
    print(f"W przypadku debugowania dodaj --debug")
    #Remove-Item -Recurse -Force .\chroma_db
    history = load_history()
    
    while True:
        try:
            query = input("\nTwoje pytanie: ").strip()
        except KeyboardInterrupt:
            print("\nZakończono.")
            break
        
        if not query:
            continue
        if query.lower() in {"q", "exit", "quit", "e", "end"}:
            print("Zakończono.")
            break
        if query.lower() in {"clear", "cls"}:
            history.clear()
            print("Historia czyszczona.")
            continue
        if query.lower() =="debug":
            debug_mode = not debug_mode
            continue
        print("Przetwarzanie...")
        

        t1 = time.time()
        context_chunks = retrieve(query, collection, debug=debug_mode)
        t2 = time.time()
        answer = generate_answer(query, context_chunks, history)
        t6 = time.time()   
        if query.lower() not in COMMANDS:
            history.append((query, answer))
            save_history(history)
        t7 = time.time()
        print(answer)
        print(f"\n⏱ Retrieve: {t2-t1:.2f}s | LLM: {t6-t2:.2f}s | Save: {t7-t6:.2f}s")
    

if __name__ == "__main__":
    main()   