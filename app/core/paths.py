import os
from kivy.app import App

def get_data_dir():
    """
    Returns the app's private storage directory on Android.
    This is where the app can store user data safely.
    """
    return App.get_running_app().user_data_dir


def get_recordings_dir():
    """
    Returns the directory for storing recordings inside the app's private storage.
    If the directory doesn't exist, it creates it.
    """
    recordings_dir = os.path.join(get_data_dir(), 'recordings')
    
    if not os.path.exists(recordings_dir):
        os.makedirs(recordings_dir)
    
    return recordings_dir