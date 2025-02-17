# -*- coding: utf-8 -*-
import gradio as gr
from langchain_community.document_loaders import CSVLoader
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain.chains import ConversationalRetrievalChain
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.vectorstores import Chroma
import dotenv
import os

# Load environment variables
dotenv.load_dotenv()

# Initialize models
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY not found in environment variables")

os.environ['OPENAI_API_KEY'] = api_key
embeddings_model = OpenAIEmbeddings(model="text-embedding-3-large")
llm = ChatOpenAI(model="gpt-4o-mini")

# Load and process CSV files
csv_paths = [
    "/home/sanju/Intern_VH/Learning-GEN-AI/Tutorials/Langchain/Data/DiseaseAndSymptoms.csv",
    "/home/sanju/Intern_VH/Learning-GEN-AI/Tutorials/Langchain/Data/Diseaseprecaution.csv"
]

# Check if vector store exists
if not os.path.exists("./chroma_db"):
    print("Creating new vector store...")
    documents = []
    for path in csv_paths:
        loader = CSVLoader(file_path=path)
        documents.extend(loader.load())
        print(f"Loaded {len(documents)} documents from {path}")
    
    # Split documents
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    all_splits = text_splitter.split_documents(documents)
    
    # Create new vector store
    vector_store = Chroma.from_documents(
        documents=all_splits,
        embedding=embeddings_model,
        persist_directory="./chroma_db"
    )
else:
    print("Loading existing vector store...")
    vector_store = Chroma(
        persist_directory="./chroma_db",
        embedding_function=embeddings_model
    )

# Create conversation chain
qa_chain = ConversationalRetrievalChain.from_llm(
    llm,
    vector_store.as_retriever(search_kwargs={'k': 3}),
    return_source_documents=True
)

# Custom CSS for styling
custom_css = """
#references-box {
    padding: 15px;
    background: #1e1e2e; /* Dark theme background to match UI */
    border-radius: 8px;
    max-height: 400px;
    overflow-y: auto;
    border: 1px solid #444;
    font-size: 14px;
    color: #e0e0e0;
    font-family: 'Arial', sans-serif;
}

.ref-item {
    margin-bottom: 12px;
    padding: 12px;
    background: #282838; /* Slightly lighter than the background */
    border-radius: 6px;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
    border-left: 4px solid #00C896; /* Medical green for a subtle highlight */
    font-family: 'Arial', sans-serif;
    color: #f0f0f0 !important;
    transition: all 0.3s ease-in-out;
}

.ref-item:hover {
    background: #303048; /* Slight highlight on hover */
    border-left: 4px solid #4CAF50; /* Brighter green accent */
}

.ref-item b {
    color: #ffffff !important;
    font-size: 15px;
}

.ref-item i {
    color: #b0b0b0 !important;
}

/* Scrollbar Styling */
#references-box::-webkit-scrollbar {
    width: 8px;
}

#references-box::-webkit-scrollbar-thumb {
    background: #555;
    border-radius: 4px;
}

#references-box::-webkit-scrollbar-thumb:hover {
    background: #777;
}
"""
def format_sources(source_docs):
    """Format source documents for display, removing duplicates"""
    seen_sources = set()
    formatted = []
    
    for doc in source_docs:
        source = doc.metadata.get('source', 'Unknown CSV')
        if source in seen_sources:
            continue
        seen_sources.add(source)
        
        content = doc.page_content[:250] + "..." if len(doc.page_content) > 250 else doc.page_content
        formatted.append(f"""
        <div class="ref-item">
            <b>Source:</b> {source.split('/')[-1]}<br>
            <i>Content:</i> {content}
        </div>
        """)
    return "\n".join(formatted) if formatted else "<p style='color:#bbb;'>No sources found</p>"

def respond(message, chat_history):
    """Handle user query and update interface"""
    # Run the QA chain
    result = qa_chain.invoke({
        "question": message,
        "chat_history": [(q, a) for q, a in chat_history]
    })
    
    # Get response and sources
    answer = result['answer']
    sources = format_sources(result['source_documents'])
    
    # Update chat history
    chat_history.append((message, answer))
    
    # Return updated components
    return "", chat_history, sources

# Build the Gradio interface
with gr.Blocks(css=custom_css, theme=gr.themes.Soft()) as demo:
    with gr.Row():
        with gr.Column(scale=2):
            gr.Markdown("# Medical Knowledge Assistant 🩺")
            gr.Markdown("Ask questions about diseases, symptoms, and precautions")
            chatbot = gr.Chatbot(height=500)
            msg = gr.Textbox(label="Your Question", placeholder="Type your medical query here...")
            clear = gr.Button("Clear Chat")

        with gr.Column(scale=1):
            gr.Markdown("## Reference Sources 📚")
            sources_box = gr.HTML(elem_id="references-box", value="<p style='color: #555; font-size:14px;'>Sources will appear here...</p>")

    # Event handling
    msg.submit(
        respond,
        [msg, chatbot],
        [msg, chatbot, sources_box]
    )
    clear.click(lambda: (None, [], ""), None, [msg, chatbot, sources_box])

# Launch the app
if __name__ == "__main__":
    demo.launch(share=True)