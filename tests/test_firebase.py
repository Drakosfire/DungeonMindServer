# test_firebase.py
import pytest 
import firebase_admin
from firebase_admin import credentials, firestore

def get_client():
    cred = credentials.Certificate("./serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    return db

@pytest.mark.focus
def test_firebase():
    db = get_client()
    db.collection('files').add({'name': 'test.txt', 'content': 'test content'})
