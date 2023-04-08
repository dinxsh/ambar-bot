import pymongo

uri = "mongodb+srv://dineshtalwadker:omshanti2005@ambar.shkhbep.mongodb.net/test"
client = pymongo.MongoClient(uri)
db = client.data

col = db["badge"]
print(col)