"""News feeds the pipeline reads. Add, remove or reorder freely.

A feed that fails to load is skipped, so a dead URL never breaks a run.
X/Twitter has no free feed, so posts there reach the radar through the
news coverage below.
"""

FEEDS = [
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("Ars Technica AI", "https://arstechnica.com/ai/feed/"),
    ("MIT Technology Review AI", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
    ("The Decoder", "https://the-decoder.com/feed/"),
    ("OpenAI News", "https://openai.com/news/rss.xml"),
    ("Google AI Blog", "https://blog.google/technology/ai/rss/"),
    ("Google DeepMind", "https://deepmind.google/blog/rss.xml"),
    ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
    ("Simon Willison", "https://simonwillison.net/atom/everything/"),
    (
        "Hacker News (AI, 150+ points)",
        "https://hnrss.org/newest?q=AI+OR+LLM+OR+GPT+OR+Claude+OR+Gemini+OR+Anthropic+OR+OpenAI&points=150",
    ),
]
