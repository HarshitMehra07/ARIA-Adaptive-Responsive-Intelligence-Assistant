class WebsiteChecker:

    SAFE_DOMAINS = [

        "openai.com",

        "google.com",

        "github.com",

        "microsoft.com"

    ]

    @staticmethod
    def verify(url):

        for domain in WebsiteChecker.SAFE_DOMAINS:

            if domain in url:

                return "verified"

        return "unknown"