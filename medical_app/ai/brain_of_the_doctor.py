import base64
from mimetypes import guess_type

from groq import Groq


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        encoded_image = base64.b64encode(image_file.read()).decode("utf-8")

    mime_type, _ = guess_type(str(image_path))
    return encoded_image, mime_type or "image/jpeg"


def analyze_image_with_query(query, encoded_image, model, mime_type="image/jpeg"):
    client = Groq()
    content = [{"type": "text", "text": query}]

    if encoded_image:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{encoded_image}",
                },
            }
        )

    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": content}],
        model=model,
    )

    return chat_completion.choices[0].message.content
