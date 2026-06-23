from internet.search_engine import SearchEngine
from internet.website_checker import WebsiteChecker
from internet.source_compare import SourceCompare

class InternetBrain:

    @staticmethod
    def investigate(query):

        results = SearchEngine.search(
            query
        )

        comparison = (
            SourceCompare.compare(
                results
            )
        )

        return {

            "results": results,

            "comparison": comparison

        }

    @staticmethod
    def verify(url):

        return WebsiteChecker.verify(
            url
        )