"""
This module handles the Vector Memory interface using Pinecone.
It allows agents to store and retrieve semantic data (news, financials, analysis).
"""

import os
import time
from typing import List, Optional
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from dotenv import load_dotenv

load_dotenv()


class VectorMemory:
    """
    Shared Memory for the FinResearch AI system using Pinecone.
    """

    def __init__(self):
        self.api_key = os.getenv("PINECONE_API_KEY")
        self.index_name = os.getenv("PINECONE_INDEX_NAME", "finresearch-index")

        if not self.api_key:
            raise ValueError("PINECONE_API_KEY is not set in environment variables.")

        # Initialize Embeddings
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

        # Initialize Vector Store
        self.vector_store = PineconeVectorStore(
            index_name=self.index_name,
            embedding=self.embeddings,
            pinecone_api_key=self.api_key,
        )

    def add_documents(self, documents: List[Document], source: str = "unknown"):
        """
        Add documents to the Pinecone index.
        Args:
            documents: List of LangChain Documents.
            source: Metadata tag for the source (e.g., "Tavily", "YFinance").
        """
        current_time = time.time()

        # Add metadata source if not present
        for doc in documents:
            if "source" not in doc.metadata:
                doc.metadata["source"] = source
            # Add timestamp for caching logic
            doc.metadata["timestamp"] = current_time

        self.vector_store.add_documents(documents)
        print(f"Added {len(documents)} documents to Pinecone.")

    def similarity_search(
        self, query: str, k: int = 5, filter: Optional[dict] = None
    ) -> List[Document]:
        """
        Perform vector similarity search.
        Args:
            query: The text query.
            k: Number of results to return.
            filter: Metadata filter dict.
        """
        return self.vector_store.similarity_search(query, k=k, filter=filter)
