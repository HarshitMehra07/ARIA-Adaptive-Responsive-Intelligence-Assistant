class MemoryCore:

    def __init__(self):
        self.short_term = []

    def add_memory(self, text):
        self.short_term.append(text)

    def get_recent(self):
        return self.short_term[-10:]