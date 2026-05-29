import os
import json
import requests
from dotenv import load_dotenv

load_dotenv('/home/gaston/htdocs/opera.bot/.env')
LINE_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')

HEADERS = {
    'Authorization': f'Bearer {LINE_ACCESS_TOKEN}',
    'Content-Type': 'application/json'
}

rich_menu_data = {
    "size": {
        "width": 2500,
        "height": 1686
    },
    "selected": True,
    "name": "Opéra Taipei Main Menu",
    "chatBarText": "Menu",
    "areas": [
        {
            "bounds": {"x": 0,    "y": 0,   "width": 833,  "height": 843},
            "action": {"type": "postback", "data": "action=reservation", "displayText": "Reservations"}
        },
        {
            "bounds": {"x": 833,  "y": 0,   "width": 833,  "height": 843},
            "action": {"type": "postback", "data": "action=drinks_menu", "displayText": "Drinks Menu"}
        },
        {
            "bounds": {"x": 1666, "y": 0,   "width": 834,  "height": 843},
            "action": {"type": "postback", "data": "action=food_menu",   "displayText": "Food Menu"}
        },
        {
            "bounds": {"x": 0,    "y": 843, "width": 833,  "height": 843},
            "action": {"type": "uri", "uri": "https://www.instagram.com/operataipei/"}
        },
        {
            "bounds": {"x": 833,  "y": 843, "width": 833,  "height": 843},
            "action": {"type": "postback", "data": "action=contact_staff", "displayText": "Contact Us"}
        },
        {
            "bounds": {"x": 1666, "y": 843, "width": 834,  "height": 843},
            "action": {"type": "postback", "data": "action=info_hours",    "displayText": "Info & Hours"}
        }
    ]
}

def create_and_deploy_rich_menu():
    print("Création de la structure du Rich Menu Opéra...")
    response = requests.post(
        'https://api.line.me/v2/bot/richmenu',
        headers=HEADERS,
        data=json.dumps(rich_menu_data)
    )
    if response.status_code != 200:
        print(f"❌ Erreur création menu : {response.text}")
        return

    rich_menu_id = response.json().get('richMenuId')
    print(f"✅ Rich Menu créé : {rich_menu_id}")

    image_path = '/home/gaston/htdocs/opera.bot/assets/operarichmenu_compressed.jpg'
    print("Upload de l'image...")
    with open(image_path, 'rb') as f:
        upload_res = requests.post(
            f'https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content',
            headers={
                'Authorization': f'Bearer {LINE_ACCESS_TOKEN}',
                'Content-Type': 'image/jpeg'
            },
            data=f
        )
        if upload_res.status_code != 200:
            print(f"❌ Erreur upload image : {upload_res.text}")
            return
        print("✅ Image uploadée.")

    print("Activation du menu par défaut...")
    set_default_res = requests.post(
        f'https://api.line.me/v2/bot/user/all/richmenu/{rich_menu_id}',
        headers=HEADERS
    )
    if set_default_res.status_code == 200:
        print("✅ Rich Menu Opéra Taipei en ligne !")
    else:
        print(f"❌ Erreur activation : {set_default_res.text}")

if __name__ == "__main__":
    create_and_deploy_rich_menu()
