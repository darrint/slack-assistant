def post(client, channel: str, text: str):
    client.chat_postMessage(channel=channel, text=text)
