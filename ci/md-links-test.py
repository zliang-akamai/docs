#!/usr/bin/env python
import os
import sys
import re
import frontmatter
import random
import textwrap

class Guide:
    def __init__(self, path, title, link):
        self.path = path
        self.title = title
        self.link = link
        self.aliases = []
        self.assets = []
        self.anchors = []
        self.issues = []
        self.logged = False

    def add_aliases(self, aliases):
        self.aliases = aliases

    def add_asset(self, asset):
        self.assets.append(asset)

    def add_anchor(self, anchor):
        self.anchors.append(anchor)

    def add_issue(self, issue):
        self.issues.append(issue)

    def log_guide(self):
        self.logged = True

class Asset:
    def __init__(self, link):
        self.link = link

class Alias:
    def __init__(self, link, guide):
        self.link = link
        self.guide = guide

class Issue:
    def __init__(self, link, type_id):
        self.link = link
        self.type_id = type_id
        self.affected_guides = []
        self.notes = ""

    def add_guide(self, guide):
        self.affected_guides.append(guide)

    def add_notes(self, notes):
        self.notes = notes

class IssueType:
    def __init__(self, id, title, summary, severity, weight):
        self.id = id
        self.title = title
        self.summary = summary
        self.severity = severity
        self.weight = weight
        self.num_issues = 0
        self.issues= []

    def set_num_issues(self, count):
        self.num_issues = count

    def add_issue(self, issue):
        self.issues.append(issue)

DOCS_DIR = [
    "docs/guides",
    "docs/products",
    "docs/bundles",
    "docs/assets",
    "docs/api",
    "docs/reference-architecture"
]

# Create all issue types
issue_types = []
issue_types.append(IssueType(
    id = 'not-found',
    title = "Target not found",
    summary = "The link's target has not been found (would likely result in a 404 error).",
    severity = 'failure',
    weight = 0
))
issue_types.append(IssueType(
    id = 'duplicate-alias',
    title = "Duplicate alias",
    summary = "This alias appears in multiple guides.",
    severity = 'failure',
    weight = 10
))
issue_types.append(IssueType(
    id = 'docs-domain-name',
    title = "Contains domain name",
    summary = "The link contains the domain name of the docs site.",
    severity = 'failure',
    weight = 20
))
issue_types.append(IssueType(
    id = 'incorrect-root',
    title = "Incorrect root directory",
    summary = "The link does not point to the correct root (/docs/)",
    severity = 'failure',
    weight = 30
))
issue_types.append(IssueType(
    id = 'other',
    title = "Other issues",
    summary = "The link contains other unspecified issues, like extra characters or incorrect formatting.",
    severity = 'failure',
    weight = 40
))
issue_types.append(IssueType(
    id = 'points-to-alias',
    title = "Target is alias",
    summary = "The link points to an alias of guide instead of its current URL.",
    severity = 'warning',
    weight = 50
))

# ------------------
# Build a list of all guides
# ------------------
def get_guides():

    guides = []
    assets = []

    # Add top level guides
    guides.append(Guide("docs/_index.md", "Docs Home", "/docs/"))
    guides.append(Guide("", "Marketplace", "/docs/marketplace/"))
    guides.append(Guide("", "Resources", "/docs/resources/"))
    guides.append(Guide("", "Q&A", "/docs/topresults/?docType=community"))

    # Iterate through each file in each docs directory
    for dir in DOCS_DIR:
        for root, dirs, files in os.walk(dir):
            for file in files:

                # The relative file path of the file
                file_path = os.path.join(root, file)

                # If the file is markdown..
                if file.endswith('.md'):
                    try:
                        # Loads the entire guide (including front matter)
                        expanded_guide = frontmatter.load(file_path)

                        # Ignores the guide if it's headless
                        if "headless" in expanded_guide.keys():
                            if expanded_guide["headless"] == True:
                                continue

                        # Identifies the canonical link for a guide
                        if "slug" in expanded_guide.keys() and "docs/guides/" in file_path:
                            canonical_link = "/docs/guides/" + expanded_guide['slug'] + "/"
                        elif "slug" in expanded_guide.keys() and "docs/api/" in file_path:
                            canonical_link = "/docs/api/" + expanded_guide['slug'] + "/"
                        else:
                            canonical_link = "/" + file_path
                            canonical_link = canonical_link.replace('/index.md','/')
                            canonical_link = canonical_link.replace('/_index.md','/')

                        # Construct the guide object
                        guide = Guide(file_path, expanded_guide['title'], canonical_link)

                        # Add aliases to the guide object if they exist
                        if "aliases" in expanded_guide.keys():
                            guide.add_aliases(expanded_guide['aliases'])

                        # Append the guide object to the list of guides
                        guides.append(guide)
                    except Exception as e: print(e)

                # If the file is something else, like an image or other asset...
                else:
                    file_path = os.path.join(root, file)
                    path_segments = file_path.split("/")
                    if "docs/guides/" in file_path:
                        link = "/docs/guides/" + path_segments[-2] + "/" + path_segments[-1]
                    else:
                        link = "/" + file_path
                    assets.append(Asset(link))

    return guides, assets

# ------------------
# Check for duplicate aliases
# ------------------
def get_duplicate_aliases(guides):

    aliases = set()
    issues = []

    for guide in guides:
      for alias in guide.aliases:
        if alias in aliases:
          issues.append(Issue(alias,'duplicate-alias'))
        else:
          aliases.add(alias)

    return issues

# ------------------
# Check internal links
# ------------------
def check_internal_markdown_links(guides, assets):

    # The regex pattern used to locate all markdown links containing the string "/docs".
    # This bypasses any external urls and archor links
    link_pattern = re.compile("(?:[^\!]|^)\[([^\[\]]+)\]\(()([^()]+)\)")

    # Array of special elements to ignore
    elementsToIgnore = ['{{< file', '```', '{{< command']

    issues = []

    for guide in guides:

        # Ignore guides with no file path
        if guide.path == "":
            continue

        expanded_guide = frontmatter.load(guide.path)

        # Reset insideSpecialElement for each new file
        insideSpecialElement = False

        # Iterate through each line of the file
        for i, line in enumerate(open(guide.path)):

            # Ignore certain code elements
            if line.strip().startswith(tuple(elementsToIgnore)):
                insideSpecialElement = True
                continue
            elif line.strip().startswith(tuple(elementsToIgnore)):
                insideSpecialElement = False
                continue
            if insideSpecialElement == True:
                continue

            # Find and iterate through all markdown links to other guides
            for match in re.finditer(link_pattern, line):
                # Remove the title, brackets, and parenthesis from the markdown link syntax
                link = match.group(3)
                link_unmodified = link
                # Log issue if link contains "linode.com/docs/"
                if "linode.com/docs/" in link:
                    issues.append(Issue(link_unmodified,'docs-domain-name'))
                    continue
                # Ignore links that start with common protocols
                if link.startswith('http://') or link.startswith('https://') or link.startswith('ftp://'):
                    continue
                # Check if link points to an asset link
                if next((x for x in assets if x.link == link), None):
                    continue
                # Ignore anchors
                if link.startswith('#'):
                    continue
                elif "#" in link:
                    link = link.split("#", 1)[0]
                # Ignore links to resources within the same directory
                if not "/" in link and "." in link:
                    continue
                # Log issue if link does not start with /docs/
                if not link.startswith('/docs/'):
                    issues.append(Issue(link_unmodified,'incorrect-root'))
                    continue
                # Log issue if link ends with two slashes /
                if '//' in link:
                    # Log issue if link ends with two slashes /
                    issues.append(Issue(link_unmodified,'formatting'))
                    link = link.replace('//','/')
                if not link.endswith('/'):
                    # Log warning if link does not end with a slash /
                    issues.append(Issue(link_unmodified,'formatting'))
                    link = link + '/'
                # Check if link points to a canonical internal link
                if not next((x for x in guides if x.link == link), None):
                    # Checks if the link matches an alias or not
                    if next((x for x in guides if link.replace('/docs/','/') in x.aliases), None) is not None:
                        issues.append(Issue(link_unmodified,'points-to-alias'))
                    else:
                        issues.append(Issue(link_unmodified,'not-found'))
    return issues

# ------------------
# Main function
# ------------------
def main():

    test_failed = False
    issues = []
    guides, assets = get_guides()

    issues = issues + (get_duplicate_aliases(guides))
    issues = issues + (check_internal_markdown_links(guides, assets))

    # Iterate through each issue type. Then, iterate through all issues
    # and add issues belonging to the specified issue type.
    for t in issue_types:
      for i in issues:
        if i.type_id == t.id:
            t.add_issue(i)

    # Sorts the issue type based on the weight
    issue_types.sort(key=lambda x: x.weight)

    # Check if there are any failures. If so, set test_failed to true
    for t in issue_types:
      if t.severity == 'failure' and not len(t.issues) == 0:
        test_failed = True
        break

    # Output Summary
    print(textwrap.dedent(f"""
    {'='*40}

    MARKDOWN LINK TESTER

    This test analyzes the markdown links within our library.
    Valid external links (links pointing to other sites) are ignored.
    Otherwise, if the link is not valid or does not point to a
    guide or asset on the docs site, an issue is logged.

    Number of guides: {str(len(guides))} (with {str(len(assets))} assets)
    """))

    for t in issue_types:
      print(f"    {t.title} ({(t.severity).upper()}): {str(len(t.issues))}")

    # Output the result of the test. If the test has failed, return a
    # failure to GitHub Actions.
    if not test_failed:
        print(textwrap.dedent(f"""
        TEST SUCCEEDED!

        {'='*40}
        """))
    else:
        print(textwrap.dedent(f"""
        TEST FAILED!

        {'='*40}
        """))

        # Output information about each issue type and any associated issues
        for t in issue_types:
          if t.severity == 'failure' and not len(t.issues) == 0:
            # Output heading for this issue type
            print(textwrap.dedent(f"""
              {t.title} ({(t.severity).upper()}): {str(len(t.issues))}
                  {t.summary}
              """))
            # Output the list of errors if the issue severity is a failure
            for i in t.issues:
              print(f"    - {i.link}")

        sys.exit(1)

if __name__ == "__main__":
    main()