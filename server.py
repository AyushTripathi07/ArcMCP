from gradio_client import Client

client = Client("abidlabs/image_generator")
client.predict(text="an astronaut riding a camel", steps=25)