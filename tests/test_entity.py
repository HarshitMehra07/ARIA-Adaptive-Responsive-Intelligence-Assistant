from memory.entity_extractor import EntityExtractor

print("Entity Tests")

entities = EntityExtractor.extract(
    "I am learning Python, Machine Learning and Deep Learning"
)

print(entities)