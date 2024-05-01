import re
import pandas as pd
from langdetect import detect


def drop_non_english_sentences(df: pd.DataFrame, column_name: str) -> pd.DataFrame:
    """
    Filter a DataFrame to exclude rows containing sentences that are not in the English language.

    Parameters:
    - df (pandas.DataFrame): The input DataFrame.
    - column_name (str): The name of the column in which to check for English sentences.

    Returns:
    - pandas.DataFrame: A new DataFrame containing only rows with English sentences in the specified column.
    """
    def is_english_sentence(text: str) -> bool:
        """
        Check if a given text is in the English language.

        Parameters:
        - text (str): The text to check.

        Returns:
        - bool: True if the text is in English, False otherwise.
        """
        try:
            return detect(text) == 'en' if text.strip() else False
        except:
            return False

    return df[df[column_name].apply(is_english_sentence)]



def preprocessing(df: pd.DataFrame, col_name: str) -> pd.DataFrame:
    """
    Preprocess the specified column of a DataFrame by removing emojis.
    Args:
        df (pd.DataFrame): The input DataFrame.
        col_name (str): The name of the column to preprocess.
    Returns:
        pd.DataFrame: The preprocessed DataFrame.
    """
    emoji_patterns = [
        "[\U0001F600-\U0001F64F]",  
        "[\U0001F300-\U0001F5FF]",  
        "[\U0001F680-\U0001F6FF]",  
        "[\U0001F1E0-\U0001F1FF]",  
        "[\U00002500-\U00002BEF]",  
        "[\U00002702-\U000027B0]",
        "[\U000024C2-\U0001F251]",
        "[\U0001f926-\U0001f937]",
        "[\U00010000-\U0010ffff]",
        "[\u2640-\u2642]",
        "[\u2600-\u2B55]",
        "[\u200d]",
        "[\u23cf]",
        "[\u23e9]",
        "[\u231a]",
        "[\ufe0f]",  
        "[\u3030]"
    ]
    emoji_pattern = re.compile("|".join(emoji_patterns))
  
    def remove_emojis(text: str) -> str:
        """
        Remove emojis from the given text.
        Args:
            text (str): The input text.
        Returns:
            str: The text with emojis removed.
        """
        return emoji_pattern.sub(r'', text)
    
    df[col_name] = df[col_name].apply(remove_emojis)
    return df



def drop_short_rows(data_frame: pd.DataFrame, column_name: str) -> pd.DataFrame:
    """
    Drop rows from a DataFrame where the text in the specified column has 10 or fewer words.

    Args:
        data_frame (pd.DataFrame): The DataFrame to process.
        column_name (str): The name of the column containing the text.

    Returns:
        pd.DataFrame: A new DataFrame with short rows removed.
    """
    # Create a mask to filter out rows with text containing 10 or fewer words
    mask = data_frame[column_name].apply(lambda text: len(str(text).split()) > 10)
    filtered_df = data_frame[mask]

    return filtered_df



def trim_long_rows(dataframe: pd.DataFrame, column_name: str, max_words: int) -> pd.DataFrame:
    """
    Trim rows in the specified column that have more than max_words words.
    
    Args:
        dataframe (pd.DataFrame): The DataFrame containing the data.
        column_name (str): The name of the column to process.
        max_words (int, optional): Maximum allowed word count for rows.
        
    Returns:
        pd.DataFrame: The updated DataFrame with trimmed rows.

        test comment
    """
    if column_name not in dataframe.columns:
        return dataframe
    
    def trim_words(cell_value):
        if pd.isnull(cell_value):
            return cell_value
        words = str(cell_value).split()
        if len(words) > max_words:
            return " ".join(words[:max_words])
        return cell_value

    dataframe[column_name] = dataframe[column_name].apply(trim_words)
    
    return dataframe