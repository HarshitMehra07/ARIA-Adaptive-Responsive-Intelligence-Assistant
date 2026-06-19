from memory.memory_compressor import MemoryCompressor

memories = [

    "I go gym every day",

    "Fitness is important to me",

    "Gym helps me lose weight",

    "My goal is to become an AI Engineer",

    "I love AI",

    "AI is my future career"
]

result = MemoryCompressor.compress(memories)

print(result)