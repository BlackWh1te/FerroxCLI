"""Semantic search using sentence-transformers and FAISS"""

import json

import faiss
from sentence_transformers import SentenceTransformer


class SemanticSearch:
    """Semantic search using sentence-transformers and FAISS for vector similarity"""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize semantic search

        Args:
            model_name: Name of the sentence-transformers model to use
        """
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self.index = None
        self.documents = []
        self.dimension = None

    def index_documents(self, documents: list[str]) -> None:
        """
        Index documents for semantic search

        Args:
            documents: List of document strings to index
        """
        self.documents = documents

        if not documents:
            return

        # Generate embeddings
        embeddings = self.model.encode(documents)

        # Initialize FAISS index
        self.dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatL2(self.dimension)

        # Add embeddings to index
        self.index.add(embeddings.astype("float32"))

    def search(self, query: str, k: int = 5) -> list[tuple[str, float]]:
        """
        Search for similar documents

        Args:
            query: Search query string
            k: Number of results to return

        Returns:
            List of tuples (document, distance) sorted by similarity
        """
        if self.index is None or not self.documents:
            return []

        # Generate query embedding
        query_embedding = self.model.encode([query])

        # Search index
        distances, indices = self.index.search(query_embedding.astype("float32"), k)

        # Format results
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if 0 <= idx < len(self.documents):
                results.append((self.documents[idx], float(dist)))

        return results

    def save_index(self, file_path: str) -> None:
        """
        Save the index and documents to disk

        Args:
            file_path: Path to save the index (without extension)
        """
        if self.index is None:
            raise ValueError("No index to save")

        # Save FAISS index
        faiss.write_index(self.index, f"{file_path}.index")

        # Save documents and metadata
        metadata = {
            "documents": self.documents,
            "model_name": self.model_name,
            "dimension": self.dimension,
        }

        with open(f"{file_path}.metadata", "w", encoding="utf-8") as f:
            json.dump(metadata, f)

    def load_index(self, file_path: str) -> None:
        """
        Load the index and documents from disk

        Args:
            file_path: Path to load the index from (without extension)
        """
        # Load FAISS index
        self.index = faiss.read_index(f"{file_path}.index")

        # Load metadata
        with open(f"{file_path}.metadata", encoding="utf-8") as f:
            metadata = json.load(f)

        self.documents = metadata["documents"]
        self.model_name = metadata["model_name"]
        self.dimension = metadata["dimension"]

        # Reinitialize model if needed
        if self.model_name != self.model.get_sentence_embedding_dimension_name():
            self.model = SentenceTransformer(self.model_name)

    def clear_index(self) -> None:
        """Clear the current index and documents"""
        self.index = None
        self.documents = []
        self.dimension = None
