class GenerationManager:
    @staticmethod
    def generate_content(request_type: str, context: str) -> str:
        """
        Handles requests for code, documents, or presentations.
        """
        if "code" in request_type:
            return f"```python\n# Generated code for: {context}\nprint('Hello ARIA')\n```"
        elif "ppt" in request_type:
            return f"I'm generating a PowerPoint presentation based on: {context}. (Simulated)"
        else:
            return f"I've prepared the document you requested: {context}"
