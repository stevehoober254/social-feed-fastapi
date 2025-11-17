from dotenv import load_dotenv
load_dotenv()

import os
from imagekitio import ImageKit

# Get environment variables
private_key = os.getenv("IMAGEKIT_PRIVATE_KEY")
public_key = os.getenv("IMAGEKIT_PUBLIC_KEY")
url_endpoint = os.getenv("IMAGEKIT_URL_ENDPOINT")

# Check if all required environment variables are set
if not private_key or not public_key or not url_endpoint:
    raise ValueError("Missing ImageKit configuration. Please set IMAGEKIT_PRIVATE_KEY, IMAGEKIT_PUBLIC_KEY, and IMAGEKIT_URL_ENDPOINT in your .env file.")

imagekit = ImageKit(
    private_key=private_key,
    public_key=public_key,
    url_endpoint=url_endpoint
)