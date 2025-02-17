import os
import faiss
import numpy as np
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document
from pypdf import PdfReader
from io import BytesIO
from dotenv import load_dotenv
from pydantic import BaseModel
import openai


# Directly set your OpenAI API key
openai.api_key = "OPENAI_API_KEY"

# Initialize OpenAI client (no need to pass the API key again)
client = openai

# Initialize FastAPI
app = FastAPI()

# Serve static frontend files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve index.html when accessing the root
@app.get("/")
async def serve_frontend():
    return FileResponse("static/index.html")

# Initialize FAISS Index
index = None
embeddings = OpenAIEmbeddings(openai_api_key=openai.api_key)

def extract_text_from_pdf(file_content: BytesIO):
    """Extracts text from a PDF file."""
    pdf_reader = PdfReader(file_content)
    text = "\n".join([page.extract_text() for page in pdf_reader.pages if page.extract_text()])
    return text

def create_vector_store(text):
    """Splits text into chunks, embeds them, and stores in FAISS."""
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
    texts = text_splitter.split_text(text)
    docs = [Document(page_content=chunk) for chunk in texts]
    faiss_index = FAISS.from_documents(docs, embeddings)
    return faiss_index

@app.post("/upload/")
async def upload_document(file: UploadFile = File(...)):
    """Handles document uploads, extracts text, and indexes it in FAISS."""
    global index
    try:
        file_content = await file.read()
        document_text = extract_text_from_pdf(BytesIO(file_content))
        index = create_vector_store(document_text)
        return {"message": "Document uploaded and indexed successfully."}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

# Request model for chat
class ChatRequest(BaseModel):
    query: str

@app.post("/chat/")
async def chat_with_model(request: ChatRequest):
    """Retrieves relevant document chunks and generates a response using GPT API."""
    query = request.query  # Extract query from request

    if index is None:
        return JSONResponse(status_code=400, content={"message": "No document uploaded!"})

    relevant_docs = index.similarity_search(query, k=3)
    if not relevant_docs:
        return JSONResponse(status_code=404, content={"message": "No relevant information found in document."})

    context = "\n".join([doc.page_content for doc in relevant_docs])
    augmented_query = f"""
    You are an AI assistant that answers questions based on the provided document. Use the following context to generate a response:
    
    Document Context:
    {context}

    Question: {query}
    """

    # ✅ Updated OpenAI API call
    response = openai.ChatCompletion.create(
        model="gpt-4",  # Use "gpt-3.5-turbo" if needed
        messages=[
            {"role": "system", "content": "You are a helpful assistant that answers based on the document provided."},
            {"role": "user", "content": augmented_query}
        ],
        temperature=0.5
    )

    return {"response": response.choices[0].message.content}
