import os
from dotenv import load_dotenv
import streamlit as st

def load_api_key():
    """
    Load NewsData.io API key from environment variables.

    Returns the API key if found, otherwise shows an error in Streamlit.

    Parameters:
    None

    Returns:
    str: The NewsData.io API key if found, otherwise None.
    """
    load_dotenv()

    api_key = os.getenv("NEWSDATA_API_KEY")

    if not api_key:
        st.error("NewsData.io API key not found! Please set the NEWSDATA_API_KEY environment variable.")
        st.info("Add API key to .env file in the project: NEWSDATA_API_KEY=your_api_key_here")
        return None

    return api_key