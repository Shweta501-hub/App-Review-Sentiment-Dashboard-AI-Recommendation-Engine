import os
import sys
import re
from typing import Tuple, Dict

# Ensure project root is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.orm import Session
from database.db import SessionLocal, init_db
from database.models import Review, SentimentAnalysis


# Aspect keywords for classification rule-map (lightweight, zero-latency hybrid classifier)
ASPECT_PATTERNS: Dict[str, list] = {
    "Bug / Crash": ["crash", "freeze", "bug", "broken", "error", "fail", "not respond", "unusable", "reboot"],
    "UI / UX": ["ui", "ux", "interface", "design", "dark mode", "cluttered", "button", "layout", "animation", "navigation"],
    "Performance / Speed": ["slow", "speed", "battery", "drain", "loading", "lag", "sync", "network", "performance"],
    "Pricing / Subscription": ["price", "pricing", "subscription", "expensive", "overpriced", "cost", "pay", "payment"],
    "Feature Request": ["feature", "add", "option", "wish", "export", "support for", "would love", "please add"]
}

class SentimentAspectAnalyzer:
    def __init__(self):
        self._classifier = None

    def load_model(self):
        """Lazy load Hugging Face pipeline for sentiment analysis."""
        if self._classifier is None:
            try:
                from transformers import pipeline
                print("Loading Hugging Face DistilBERT sentiment analysis model...")
                self._classifier = pipeline(
                    "sentiment-analysis", 
                    model="distilbert-base-uncased-finetuned-sst-2-english"
                )
                print("DistilBERT model successfully loaded.")
            except Exception as e:
                print(f"Warning: Transformers library load failed ({e}). Falling back to rating-heuristic classifier.")
                self._classifier = "heuristic"

    def predict_sentiment(self, text: str, rating: int) -> Tuple[str, float]:
        """Predict sentiment label and confidence score."""
        if not text:
            return ("Neutral", 0.5)

        self.load_model()

        if self._classifier != "heuristic":
            try:
                res = self._classifier(text[:512])[0]
                label_map = {"POSITIVE": "Positive", "NEGATIVE": "Negative"}
                sentiment_label = label_map.get(res['label'], "Neutral")
                score = round(float(res['score']), 4)
                return (sentiment_label, score)
            except Exception as e:
                print(f"Inference error: {e}, falling back to rating heuristic.")

        # Fallback Heuristic using Rating
        if rating >= 4:
            return ("Positive", 0.90)
        elif rating <= 2:
            return ("Negative", 0.90)
        else:
            return ("Neutral", 0.70)

    def extract_aspect(self, text: str) -> str:
        """Extract primary product aspect from review text."""
        lower_text = text.lower()
        
        matches = {}
        for category, keywords in ASPECT_PATTERNS.items():
            score = sum(1 for kw in keywords if re.search(r'\b' + re.escape(kw) + r'\b', lower_text))
            if score > 0:
                matches[category] = score

        if matches:
            # Return category with highest keyword matches
            return max(matches, key=matches.get)
        
        return "General"

def process_unprocessed_reviews(db: Session = None):
    """Fetch unprocessed reviews, predict sentiment & aspect, and save to DB."""
    close_session = False
    if db is None:
        db = SessionLocal()
        close_session = True

    analyzer = SentimentAspectAnalyzer()
    unprocessed = db.query(Review).filter(Review.is_processed == False).all()

    if not unprocessed:
        print("No new unprocessed reviews found.")
        if close_session:
            db.close()
        return 0

    print(f"Processing sentiment analysis for {len(unprocessed)} reviews...")
    count = 0
    try:
        for rev in unprocessed:
            sentiment_label, confidence = analyzer.predict_sentiment(rev.cleaned_text or rev.review_text, rev.rating)
            aspect = analyzer.extract_aspect(rev.cleaned_text or rev.review_text)

            sentiment_entry = SentimentAnalysis(
                review_id=rev.id,
                sentiment_label=sentiment_label,
                sentiment_score=confidence,
                aspect_category=aspect
            )
            db.add(sentiment_entry)
            rev.is_processed = True
            count += 1

        db.commit()
        print(f"Successfully analyzed and updated {count} reviews.")
    except Exception as e:
        db.rollback()
        print(f"Error during sentiment processing: {e}")
    finally:
        if close_session:
            db.close()
    
    return count

if __name__ == "__main__":
    init_db()
    process_unprocessed_reviews()
