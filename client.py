from gradio_client import Client, handle_file

client = Client("prithivMLmods/Gemma-3-Multimodal")
result = client.predict(
		message={"text":"Describe this image","files":[handle_file('https://raw.githubusercontent.com/gradio-app/gradio/main/test/test_files/bus.png')]},
		param_2=1024,
		param_3=0.6,
		param_4=0.9,
		param_5=50,
		param_6=1.2,
		api_name="/chat"
)
print(result)