import openai
import os
import json

openai.api_key = os.getenv("OPENAI_API_KEY")

def decide_bid(battery_level, price, grid_stress):
    prompt = f"#prompt in here"
    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}]
    )

    return json.loads(response.choices[0].message.content) #parses and returns