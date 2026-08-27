# Global Orphan Project
Since founded in 2004, the Global Orphan (GO) Project has grown from serving a handful of children in Southeast Asia to reaching over 110,000 children annually across 11 countries, nearly 650,000 served in total, with $180M in economic impact generated. Its CarePortal platform has connected 38,000 community responders to meet the needs of 125,000 children in crisis. GO Project holds a 4/4 star Charity Navigator rating and runs on a 100% donor-covered overhead model, so every program dollar goes directly to child care.
For more about the GO Project and Databricks for Good, please see this blog.

## Problem Statement
Global Orphan (GO) Project wants to equip its outreach team with data-driven insights.
The team functions like a sales org, working to onboard users onto the platform. To enable targeted, timely outreach, we want to build a dashboard that surfaces relevant issues, each with a timestamp, citation, and confidence score, that outreach can use to craft messages that actually resonate with the recipient. For example: "Your city council is currently debating homelessness policy X. To make an impact in your community, check out Global Orphan Project."

Additionally, we want to build a knowledge graph to support meta-analysis. This piece is more experimental and open to creative direction.

## Clarification on Use Case
the use case in our mind is basically:  GO State Director gains insight on legislative action in state X.  the intel may or may not be actionable.  in the latter case, the action may be something that may or may not be limited to the given state.  in the former case, the state director can share upwards for strategic assessment.  in the latter case, the state director may use the knowledge while recruiting new careportal partners.   a hypothetical case would be a child and family welfare committee hearing where new reporting mandates are being discussed that could adversely impact some aspect of careportal.  the state director and care portal in general can work with local folks to lobby the committee and attempt to offer amended language for the bill in question.

## Requirements
### Must Have
- Web scraping for the regions listed in Appendix A: Web Scraping
- A dashboard for outreach teams, highlighting region-specific issues and facilitating targeted outreach
- Citations for all GenAI-created implementations

### Should Have
- A basic knowledge graph that allows users to visualize and analyze the scraped data

### Could Have
- Robust Named Entity Recognition (NER) for key entities e.g. location, issue, policy, etc.
- An interface allowing users to interact with the knowledge graph e.g. GUI, chat, something new!

### Won’t Have
- Production scale (CICD, robust web scraping, etc.)

## Appendix
### Appendix A: Web Scraping
To access the raw data, we recommend using basic web scraping e.g. CURL commands. Please be aware that anything behind a login wall is typically illegal to scrape; stick to the public internet. Finally, if you are looking to leverage a production API (that we used with Virtue Foundation), feel free to sign up for a free trial with Bright Data.

We are limiting to the following regions: States:  New York, California, Virginia

Here are example links to leverage as a starting point: 
- https://app.legislata.com/discover
- California: calmatters.digitaldemocracy.org
- New York: legislativelibrary.ny.gov/legislative-resources
- Virginia: lis.virginia.gov
