"""Web extraction: crawler, article parser, license checker."""

from .crawler import WebCrawler
from .license_checker import LicenseChecker, LicenseClass
from .article_parser import ArticleParser

__all__ = ["WebCrawler", "LicenseChecker", "LicenseClass", "ArticleParser"]
