import streamlit as st
import pandas as pd
import requests
import json
import time
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

# Set page config
st.set_page_config(page_title="Integrated Ad Analysis System", page_icon="📊", layout="wide")

# Authentication function
def authenticate(username, password):
    return (username == st.secrets["login_username"] and 
            password == st.secrets["login_password"])

# Function to check API rate limits
def check_rate_limits():
    try:
        response = requests.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {st.secrets['openrouter_api_key']}"},
        )
        if response.status_code == 200:
            data = response.json()['data']
            return data['rate_limit']['requests'], data['rate_limit']['interval']
        else:
            st.error("Failed to check rate limits. Please try again later.")
            return None, None
    except Exception as e:
        st.error(f"Error checking rate limits: {str(e)}")
        return None, None

# OpenRouter API call with retry logic and improved error handling
@retry(
    wait=wait_exponential(multiplier=1, min=4, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(requests.exceptions.RequestException)
)
def analyze_ad_copy(ad_copy, search_term):
    prompts = [
        "Analyze the headline effectiveness and keyword usage in this ad.",
        "Evaluate the description's informativeness and persuasiveness.",
        "Assess the call-to-action strength and unique selling proposition.",
        "Analyze the ad's relevance to search intent and emotional appeal.",
        "Provide improvement suggestions and key takeaways from this ad."
    ]
    
    full_analysis = ""
    
    for prompt in prompts:
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {st.secrets['openrouter_api_key']}",
                    "HTTP-Referer": "https://your-app-url.com",
                    "X-Title": "Ad Copy Analysis App",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "anthropic/claude-3-opus-20240229",
                    "messages": [
                        {"role": "system", "content": f"You are an expert in analyzing Google Ads copy for {search_term} products. Provide a detailed, insightful analysis that helps advertisers understand why the ad works and how to improve their own ads."},
                        {"role": "user", "content": f"""Analyze this Google Ad for {search_term} products:

{ad_copy}

{prompt}

Provide a concise but insightful analysis."""}
                    ]
                }
            )
            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content']
            full_analysis += content + "\n\n"
        except Exception as e:
            st.error(f"Error analyzing ad copy: {str(e)}")
            return None
        
        time.sleep(1)  # Respect rate limits between prompts
    
    return full_analysis

def process_dataframe(df, search_term):
    results = []
    for index, row in df.iterrows():
        ad_copy = f"Title: {row['title']}\nSnippet: {row['snippet']}\nDisplay URL: {row['displayed_link']}"
        analysis = analyze_ad_copy(ad_copy, search_term)
        
        if analysis is not None:
            results.append({
                'title': row['title'],
                'snippet': row['snippet'],
                'displayed_link': row['displayed_link'],
                'analysis': analysis
            })
            st.success(f"Successfully analyzed ad {index + 1}")
        else:
            st.error(f"Failed to analyze ad {index + 1}")
        
        time.sleep(1)  # Respect rate limits between ads
    
    return pd.DataFrame(results)

def json_to_dataframe(json_data):
    # Extract organic_results from the JSON data
    organic_results = json_data.get('organic_results', [])
    
    # Convert to DataFrame
    df = pd.json_normalize(organic_results)
    
    return df

# Main application
def main():
    st.title("Integrated Google Ads Analysis System")

    # Initialize session state
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'results' not in st.session_state:
        st.session_state.results = None

    # Login form
    if not st.session_state.logged_in:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit_button = st.form_submit_button("Login")
            
            if submit_button:
                if authenticate(username, password):
                    st.session_state.logged_in = True
                    st.rerun()  # Use st.rerun() instead of st.experimental_rerun()
                else:
                    st.error("Invalid username or password")
        return

    # Main application (only accessible after login)
    uploaded_file = st.file_uploader("Upload your JSON file", type="json")
    search_term = st.text_input("Enter the search term you used to generate this data:", "")
    
    if uploaded_file is not None and search_term:
        try:
            json_data = json.load(uploaded_file)
            df = json_to_dataframe(json_data)
            
            st.write("Converted JSON data:")
            st.write(df)

            if st.button("Analyze Ads"):
                # Check rate limits
                rate_limit, interval = check_rate_limits()
                if rate_limit is None:
                    return

                with st.spinner("Analyzing ads... This may take a few minutes."):
                    results_df = process_dataframe(df, search_term)
                    st.session_state.results = results_df

                st.success(f"Analysis complete! Successfully analyzed {len(results_df)} ads.")

            # Display results if they exist in session state
            if st.session_state.results is not None:
                st.subheader("Analysis Results:")
                for index, row in st.session_state.results.iterrows():
                    with st.expander(f"Analysis for Ad {index + 1}: {row['title']}"):
                        st.write(row['analysis'])

                # Option to download results as CSV
                csv = st.session_state.results.to_csv(index=False)
                st.download_button(
                    label="Download results as CSV",
                    data=csv,
                    file_name="ad_analysis_results.csv",
                    mime="text/csv",
                )

        except Exception as e:
            st.error(f"An error occurred while processing the file: {str(e)}")

    # Logout button
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.results = None
        st.rerun()  # Use st.rerun() instead of st.experimental_rerun()

if __name__ == "__main__":
    main()
