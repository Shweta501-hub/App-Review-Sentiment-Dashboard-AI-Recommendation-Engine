import os
import re
import pandas as pd
from datetime import datetime
from database.db import init_db, SessionLocal
from database.models import Review

def clean_text(text: str) -> str:
    """Preprocess raw review text for NLP analysis."""
    if not isinstance(text, str) or not text.strip():
        return ""
    
    # Remove HTML tags if present
    text = re.sub(r'<[^>]+>', '', text)
    # Standardize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def ingest_sample_data(csv_path: str):
    """Load, clean, and insert sample CSV reviews into SQLite DB."""
    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at {csv_path}")
        return

    print(f"Reading reviews dataset from: {csv_path}")
    df = pd.read_csv(csv_path)

    # Validate columns
    required_cols = ['review_text', 'rating']
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column '{col}' in CSV.")

    db = SessionLocal()
    count = 0
    try:
        for idx, row in df.iterrows():
            raw_text = str(row['review_text'])
            cleaned = clean_text(raw_text)
            
            # Parse date if available
            rev_date = datetime.utcnow()
            if 'review_date' in row and pd.notna(row['review_date']):
                try:
                    rev_date = datetime.strptime(str(row['review_date']), "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass

            review = Review(
                app_name="ProductivitySuite",
                app_version=str(row.get('app_version', 'v1.0')),
                author=str(row.get('author', 'Anonymous')),
                review_text=raw_text,
                cleaned_text=cleaned,
                rating=int(row['rating']),
                review_date=rev_date,
                is_processed=False
            )
            db.add(review)
            count += 1

        db.commit()
        print(f"Successfully ingested {count} reviews into the database.")
    except Exception as e:
        db.rollback()
        print(f"Failed to ingest data: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    sample_csv = os.path.join(base_dir, "data", "sample_reviews.csv")
    ingest_sample_data(sample_csv)
