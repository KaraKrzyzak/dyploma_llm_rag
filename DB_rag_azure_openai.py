"""

Przygotowanie RAGa       
    load_and_chunk()   
    CHUNKI (fragmenty tekstu ~800 znaków)   
    OllamaEmbedding() → mxbai-embed-large 
    WEKTORY zapisane w ChromaDB  - można wiele      

Każde pytanie
    retrieve() → ChromaDB.query() - wyliczamy podobienstwo 
    TOP-K chunków 
    generate_answer() - łączymy historię z top chunkami pytaniem i systemowym promtem
    wysyłanie do Azure (GPT-4o mini) 
    generujemy tekst - streaming

Trza mieć:
    pip install openai chromadb ollama

Uruchomienie:
    python rag_azure_openai.py                  # normalne uruchomienie
    python rag_azure_openai.py --rebuild        # przebuduj bazę wektorową od nowa
    python rag_azure_openai.py --debug          # pokaż pobrane chunki dla każdego pytania
    
    DO DODANIA EW - python rag_azure_openai.py --chroma_collection "COLLECTION_NAME"  - jakby było kilka RAGów
"""

import re
import sys
import time
import ollama
import chromadb
from pathlib import Path
import argparse
from chromadb import Documents, EmbeddingFunction, Embeddings
import json
from openai import AzureOpenAI
import os
from dotenv import load_dotenv

load_dotenv()

ENDPOINT        = os.getenv("OPENAI_ENDPOINT")
SUBSCRIPTION_KEY         = os.getenv("OPENAI_KEY")
DEPLOYMENT_NAME = os.getenv("DEPLOYMENT")
API_VERSION     = os.getenv("OPENAI_VERSION")
# print("OPENAI_KEY:", SUBSCRIPTION_KEY)  
# print("OPENAI_ENDPOINT:", ENDPOINT)  
# print("DEPLOYMENT:", DEPLOYMENT_NAME) 
# print("API_VERSION:", API_VERSION)



KNOWLEDGE_BASE_DIR  = "./TEXT_medic_trials/seperated_texts/"  # Folder z plikami .txt stanowiącymi bazę wiedzy RAGa.

EMBED_MODEL         = "mxbai-embed-large"   # Model embeddingowy — lokalny przez Ollama. Limit: ~512 tokenów (~500 znaków polskiego tekstu) na jeden fragment.

CHROMA_PATH         = "./chroma_db"  # Ścieżka do folderu gdzie ChromaDB zapisuje bazę wektorową na dysku.

CHROMA_COLLECTION   = "medical_kb"  # Nazwa kolekcji w ChromaDB. Przy innym RAGu/wsadzie danych inna kolekcja, żeby się nie mieszały.

CHUNK_SIZE          = 800 # Maksymalna liczba znaków w jednym chunku.

CHUNK_OVERLAP       = 3 # Ile zdań z poprzedniego chunku jest powtarzanych na początku kolejnego. 

TOP_K               = 6 # Ile najbardziej pasujących chunków jest pobieranych dla każdego pytania. Po zmianie na AZURE zwiększamy z 4 do 6

HISTORY_LENGTH      = 5 # Ilość zapytań używanych jako historia kontekstu

HISTORY_FILE        = "./history.json" # Plik JSON gdzie zapisywana jest historia rozmów między sesjami.


SYSTEM_PROMPT = """Jesteś medycznym asystentem pomagającym pacjentom i ich rodzinom zrozumieć wyniki badań medycznych, a w szczególności wyniki badań krwi i opisy badań.

Zasady:
- Odpowiadaj wyłącznie po polsku
- Bazuj na informacjach zawartych w kontekście, który ci dostarczam; w przypadku braku napisz "Nie mam wystarczających informacji w bazie RAG" i odpowiedz ogólnie, zaznaczając "Odpowiedź z ogólnej wiedzy:"
- Używaj prostego języka zrozumiałego dla pacjenta, opisuj skomplikowane terminy medyczne w prostszy sposób
- Gdy używasz terminu medycznego, wyjaśnij go w nawiasie
- Jeśli pytanie dotyczy leczenia, zawsze dodaj: "Skonsultuj się z lekarzem przed podjęciem decyzji"
- Jeżeli znajdziesz kilka takich samych informacji, nie powielaj ich
- Jeżeli masz wylistować coś, nie powtarzaj punktów
- Dane z tabeli pokazuj tylko te, które są adekwatne do pytania
- Podawaj źródła jeżeli je znasz, na przykład nazwy dokumentów z bazy wiedzy, z których korzystałeś, w formacie: [Źródło: nazwa_pliku.txt]
"""


#Łączenie do Azure OPENAI

def create_azure_client() -> AzureOpenAI:
    client = AzureOpenAI(
    api_version=API_VERSION,
    azure_endpoint=ENDPOINT,
    api_key=SUBSCRIPTION_KEY,
)
    return client


# Embedding lokalny na danych z bazy wiedzy - Ollama, lokalnie

class OllamaEmbedding(EmbeddingFunction):
    def __init__(self):
        pass

    def __call__(self, input: Documents) -> Embeddings:
        truncated = [text[:500] for text in input]
        response = ollama.embed(model=EMBED_MODEL, input=truncated)
        return response['embeddings']


# Przygotowywanie danych: dzielenie tekstu na zdania, a następnie na chunki o maksymalnej długości CHUNK_SIZE znaków, z opcjonalnym overlapem zdań między chunkami.

def sentences_split(text: str) -> list[str]:
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return sentences


def load_and_chunk(dirpath: str, max_chars: int = CHUNK_SIZE, overlap_sents: int = CHUNK_OVERLAP) -> list:
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


# Chroma vektor - tworzy bazę wektorową na bazie wiedzy i zapisuje lokalnie

def chroma_vector(chunks: list, force_rebuild: bool = False) -> chromadb.Collection:
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    embedding_fn = OllamaEmbedding()

    if force_rebuild:
        try:
            client.delete_collection(CHROMA_COLLECTION)
            print("Stara kolekcja usunięta.")
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        embedding_function=embedding_fn,
        metadata={"description": "Medical knowledge base for RAG system"}
    )

    if collection.count() > 0:
        print(f"Kolekcja '{CHROMA_COLLECTION}' ma już {collection.count()} chunków. Pomijam indeksowanie.")
        return collection

    BATCH = 15
    for i in range(0, len(chunks), BATCH):
        batch = chunks[i: i + BATCH]
        collection.add(
            ids=[chunk["id"] for chunk in batch],
            documents=[chunk["text"] for chunk in batch],
            metadatas=[chunk["metadata"] for chunk in batch]
        )
        print(f"  [{min(i + BATCH, len(chunks))}/{len(chunks)}]")

    print(f"Zaindeksowano chunków: {collection.count()}")
    return collection


# Retrieve - pobiera najbardziej pasujące chunki z ChromaDB dla danego zapytania użytkownika.

def retrieve(query: str, collection: chromadb.Collection, top_k: int = TOP_K, debug: bool = False) -> list:
    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        include=["documents", "distances", "metadatas"]
    )

    documents = results['documents'][0]
    distances = results['distances'][0]
    metadatas = results['metadatas'][0]

    scored_chunks = [
        (doc, round(1 - dist, 3), meta)
        for doc, dist, meta in zip(documents, distances, metadatas)
    ]

    if debug:
        print(f"\nDEBUG — Top {top_k} chunków dla: '{query}'")
        for i, (doc, score, meta) in enumerate(scored_chunks):
            print(f"\n[Chunk {i+1}] Score: {score:.3f} | Źródło: {meta.get('source')} | Znaków: {meta.get('char_len')}")
            preview = doc[:500] + "..." if len(doc) > 500 else doc
            print(preview)

    return [(doc, meta.get('source', 'nieznane')) for doc, score, meta in scored_chunks]


# Generate_answer - łączy kontekst z retrieve z pytaniem użytkownika i wysyła do Azure OpenAI (GPT-4o mini) ze streamingiem odpowiedzi.

def generate_answer(
    query: str,
    context_chunks: list,
    history: list,
    azure_client: AzureOpenAI
) -> str:
    t_start = time.time()

    # Top chunki z bazy wiedzy
    context = "\n\n".join(
        f"[Źródło: {src}]\n{doc}"
        for doc, src in context_chunks
    )

    # Główny systemowy prompt
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Ładowanie historii konwersacji
    for human_message, rag_message in history[-HISTORY_LENGTH:]:
        messages.append({"role": "user",      "content": human_message})
        messages.append({"role": "assistant",  "content": rag_message})

    # Podawanie RAGa (wiedzy z bazy) i pytanie
    messages.append({
        "role": "user",
        "content": (
            f"Kontekst medyczny z bazy wiedzy:\n{context}\n\n"
            f"---\n\n"
            f"Pytanie: {query}"
        )
    })

    t_msg_ready = time.time()
    print(f"TIME: Przygotowanie wiadomości: {t_msg_ready - t_start:.2f}s")

    # Odpowiada + streaming, jak w chacie :D
    print("\n ODPOWIADAM:  : ", end="", flush=True)

    stream = azure_client.chat.completions.create(
        model=DEPLOYMENT_NAME,
        messages=messages,
        temperature=0.2,        # niska temperatura = bardziej faktyczne odpowiedzi
        max_tokens=1024,        # maksymalna długość odpowiedzi (wyjdzie koło ~750 słów)
        stream=True,            
    )

    full_response_parts = []
    for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            print(delta.content, end="", flush=True)
            full_response_parts.append(delta.content)

    print() 

    t_end = time.time()
    print(f"TIME: Azure OpenAI (GPT-4o mini): {t_end - t_msg_ready:.2f}s")

    return "".join(full_response_parts)


#ŁAdowanie i zapisywanie historii

def load_history() -> list:
    if Path(HISTORY_FILE).exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return []
                return json.loads(content)
        except json.JSONDecodeError:
            print("Error")
            return []
    return []


def save_history(history: list) -> None:
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


# Here we go again - Ruszamy!

def main():
    COMMANDS = {"q", "exit", "quit", "e", "end", "clear", "cls", "debug"}

    parser = argparse.ArgumentParser(description="Medyczny asystent RAG z Azure OpenAI (GPT-4o mini)")
    parser.add_argument(
        "--knowledge_base_dir", "-k",
        type=str,
        default=KNOWLEDGE_BASE_DIR,
        help="Ścieżka do folderu z plikami .txt bazy wiedzy"
    )  # jeżeli chcemy inny folder z bazą wiedzy
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Pokaż pobrane chunki (score, źródło, podgląd) dla każdego pytania"
    ) # jeżeli chcemy żeby nam pokazało jakie chunki nam dobiera
    parser.add_argument(
        "--rebuild", "-r",
        action="store_true",
        help="Usuń i przebuduj kolekcję ChromaDB od nowa"
    ) # jak chcemy RAGa przeliczyć ponownie
    args = parser.parse_args()

    if not Path(args.knowledge_base_dir).exists():
        print(f"Brak folderu bazy wiedzy: {args.knowledge_base_dir}")
        sys.exit(1)

    try:
        ollama.list()
    except Exception:
        print("Ollama nie działa, uruchom.")
        sys.exit(1)

    azure_client = create_azure_client()
    print(f"Połączono z: {DEPLOYMENT_NAME}")

    chunks = load_and_chunk(args.knowledge_base_dir)

    collection = chroma_vector(chunks, force_rebuild=args.rebuild)

    debug_mode = args.debug
    print("\nSystem gotowy.")
    print("------------------------------------------------------------------------")
    print("Komendy: 'q'/'exit'/'quit'/'e'/'end' → zakończ | 'clear'/'cls' → wyczyść historię | 'debug' → przełącz tryb debugowania")
    print(f"Tryb debug: {debug_mode} | Historia kontekstu: ostatnie {HISTORY_LENGTH} wymian")
    print("Witaj jestem Twoim prywatnym medycznym asystentem RAG, zadaj mi medyczne pytanie a z chęcią na nie oddpowiem! :)")
    print("------------------------------------------------------------------------")

    history = load_history()
    print(f"Wczytano {len(history)} wcześniejszych wymian z historii.")

    # Wyswietlanie rozmowy itd
    while True:
        try:
            query = input("\nTWOJE PYTANIE: ").strip()
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
            save_history(history)
            print("Historia wyczyszczona.")
            continue
        if query.lower() == "debug":
            debug_mode = not debug_mode
            print(f"Tryb debug: {'włączony' if debug_mode else 'wyłączony'}")
            continue

        print("Myślę...")

        t1 = time.time()
        context_chunks = retrieve(query, collection, debug=debug_mode)
        t2 = time.time()
        print(f"TIME: Similarity/Podobieństwo (ChromaDB lokalnie): {t2 - t1:.2f}s")

        answer = generate_answer(query, context_chunks, history, azure_client)
        t3 = time.time()

        if query.lower() not in COMMANDS:
            history.append((query, answer))
            save_history(history)
        t4 = time.time()

        print(f"TIME: Zapis historii: {t4 - t3:.2f}s")
        print(f"TIME: ŁĄCZNIE: {t4 - t1:.2f}s")


if __name__ == "__main__":
    main()