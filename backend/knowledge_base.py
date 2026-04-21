"""Knowledge base management with document loading and chunking."""
import os
from pathlib import Path
from typing import List

from langchain_community.document_loaders import (
    PyPDFLoader,
    Docx2txtLoader,
    TextLoader,
    CSVLoader,
    UnstructuredExcelLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from config import config


class KnowledgeBase:
    """Manages document loading, chunking, and vector storage in Qdrant."""
    
    def __init__(self):
        self.embeddings = None
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )
        self.vector_store: QdrantVectorStore | None = None
        self.qdrant_client: QdrantClient | None = None
        self.vector_size = 1536  # Default, will be updated based on embeddings
        
    def _get_loader(self, file_path: Path):
        """Get the appropriate loader for a file based on its extension."""
        extension = file_path.suffix.lower()
        
        loaders = {
            '.pdf': PyPDFLoader,
            '.docx': Docx2txtLoader,
            '.doc': Docx2txtLoader,
            '.txt': TextLoader,
            '.csv': CSVLoader,
            '.xlsx': UnstructuredExcelLoader,
            '.xls': UnstructuredExcelLoader,
        }
        
        loader_class = loaders.get(extension)
        if loader_class:
            return loader_class(str(file_path))
        return None
    
    def _load_documents(self) -> List[Document]:
        """Load all supported documents from the KB assets directory."""
        documents = []
        
        if not config.KB_ASSETS_DIR.exists():
            print(f"Knowledge base directory does not exist: {config.KB_ASSETS_DIR}")
            return documents
        
        supported_extensions = {'.pdf', '.docx', '.doc', '.txt', '.csv', '.xlsx', '.xls'}
        
        for file_path in config.KB_ASSETS_DIR.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
                try:
                    loader = self._get_loader(file_path)
                    if loader:
                        docs = loader.load()
                        # Add source metadata to each document
                        for doc in docs:
                            doc.metadata['source'] = file_path.name
                            doc.metadata['file_type'] = file_path.suffix.lower()
                        documents.extend(docs)
                        print(f"Loaded {len(docs)} pages/chunks from {file_path.name}")
                except Exception as e:
                    print(f"Error loading {file_path}: {e}")
                    
        return documents
    
    def _chunk_documents(self, documents: List[Document]) -> List[Document]:
        """Split documents into chunks."""
        if not documents:
            return []
        return self.text_splitter.split_documents(documents)
    
    def initialize(self, embeddings=None):
        """Initialize the knowledge base with in-memory Qdrant storage."""
        print("Initializing knowledge base...")
        
        # Ensure cache directory exists for FastEmbed and HuggingFace
        import os
        cache_dir = "/app/.cache"
        os.makedirs(cache_dir, exist_ok=True)
        os.environ["HF_HOME"] = cache_dir
        
        # Use provided embeddings or default to FastEmbed
        if embeddings is None:
            from langchain_community.embeddings import FastEmbedEmbeddings
            self.embeddings = FastEmbedEmbeddings(cache_dir=cache_dir)
        else:
            self.embeddings = embeddings
        
        # Detect vector size by embedding a test string
        test_embedding = self.embeddings.embed_query("test")
        self.vector_size = len(test_embedding)
        print(f"Detected vector size: {self.vector_size}")
        
        # Create in-memory Qdrant client
        self.qdrant_client = QdrantClient(":memory:")
        
        # Create collection with dynamic vector size
        collection_name = "knowledge_base"
        self.qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
        )
        
        # Load and chunk documents
        documents = self._load_documents()
        if documents:
            chunks = self._chunk_documents(documents)
            print(f"Created {len(chunks)} chunks from {len(documents)} documents")
            
            # Create vector store
            self.vector_store = QdrantVectorStore(
                client=self.qdrant_client,
                collection_name=collection_name,
                embedding=self.embeddings,
            )
            
            # Add documents to vector store
            self.vector_store.add_documents(chunks)
            print(f"Added {len(chunks)} chunks to vector store")
        else:
            print("No documents found in knowledge base directory")
            # Create empty vector store
            self.vector_store = QdrantVectorStore(
                client=self.qdrant_client,
                collection_name=collection_name,
                embedding=self.embeddings,
            )
    
    def search(self, query: str, k: int = 5) -> List[Document]:
        """Search the knowledge base for relevant documents."""
        if not self.vector_store:
            return []
        return self.vector_store.similarity_search(query, k=k)


# Global knowledge base instance
knowledge_base = KnowledgeBase()
