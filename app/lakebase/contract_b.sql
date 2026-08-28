-- Contract B — Gold serving tables for the GO Project outreach app (Lakebase).
-- This is the WP2 -> WP3 handoff: denormalized, app-ready opportunities plus a
-- transparent priority score, citations, and small dimensions. Hand-seeded with
-- sample rows for the WP3 self-bootstrap (not derived from silver).
--
-- Re-runnable: drops and recreates everything. Apply against `databricks_postgres`.
-- Objects live in the `gold` schema; read access is granted to PUBLIC so the
-- app's service principal can query them.

CREATE SCHEMA IF NOT EXISTS gold;
SET search_path TO gold;

DROP TABLE IF EXISTS opportunity_citations CASCADE;
DROP TABLE IF EXISTS opportunity_details CASCADE;
DROP TABLE IF EXISTS opportunity_cards CASCADE;
DROP TABLE IF EXISTS dim_issues CASCADE;
DROP TABLE IF EXISTS dim_places CASCADE;

-- Dimensions -----------------------------------------------------------------
CREATE TABLE dim_issues (
    issue_id    TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    description TEXT
);

CREATE TABLE dim_places (
    place_id       TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    state          TEXT NOT NULL,
    level          TEXT,           -- state | county | city | district
    latitude       DOUBLE PRECISION,  -- representative point for the map
    longitude      DOUBLE PRECISION
);

-- Card: one row per opportunity, denormalized for the feed --------------------
CREATE TABLE opportunity_cards (
    opportunity_id      TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    state               TEXT NOT NULL,
    place_id            TEXT REFERENCES dim_places(place_id),
    place_name          TEXT,
    issue_id            TEXT REFERENCES dim_issues(issue_id),
    issue_label         TEXT,
    relevance_direction TEXT NOT NULL,     -- opportunity | risk | watch
    signal_type         TEXT,
    event_date          DATE,
    confidence          DOUBLE PRECISION,  -- 0..1
    priority_score      DOUBLE PRECISION,  -- 0..100, transparent ranking
    source_name         TEXT,
    updated_at          TIMESTAMPTZ DEFAULT now()
);

-- Detail: one row per opportunity, the "open the card" content ----------------
CREATE TABLE opportunity_details (
    opportunity_id     TEXT PRIMARY KEY REFERENCES opportunity_cards(opportunity_id) ON DELETE CASCADE,
    summary            TEXT,
    why_it_matters     TEXT,              -- why GO / CarePortal cares
    recommended_action TEXT,              -- outreach next step
    affected_populations TEXT[],
    source_type        TEXT,
    -- transparent ranking components (feed priority_score)
    impact_magnitude   DOUBLE PRECISION,
    timing_urgency     DOUBLE PRECISION,
    locality           DOUBLE PRECISION,
    evidence_confidence DOUBLE PRECISION
);

-- Citations: one-to-many, each grounds a fact on a live page ------------------
CREATE TABLE opportunity_citations (
    citation_id    TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL REFERENCES opportunity_cards(opportunity_id) ON DELETE CASCADE,
    quote          TEXT,
    source_name    TEXT,
    source_url     TEXT,
    char_start     INT,
    char_end       INT,
    retrieved_at   TIMESTAMPTZ,
    is_primary     BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_cards_state ON opportunity_cards(state);
CREATE INDEX idx_cards_direction ON opportunity_cards(relevance_direction);
CREATE INDEX idx_citations_opp ON opportunity_citations(opportunity_id);

-- ============================================================================
-- Seed data (sample Gold — hand-authored for the WP3 bootstrap)
-- ============================================================================

INSERT INTO dim_issues (issue_id, label, description) VALUES
 ('iss-housing',  'Housing stability & homelessness', 'Housing insecurity, homelessness, eviction, shelter capacity.'),
 ('iss-foster',   'Family preservation & foster care', 'Foster care, kinship care, reunification, foster family support.'),
 ('iss-childwel', 'Child welfare & protection', 'Abuse/neglect reporting, mandates, child protective services.'),
 ('iss-youthmh',  'Youth mental health', 'Adolescent mental health, crisis services, school-based support.'),
 ('iss-poverty',  'Poverty & economic support', 'Cash assistance, tax credits, benefits, economic stability.'),
 ('iss-food',     'Food & material needs', 'Food security, material goods, basic-needs response.'),
 ('iss-edu',      'Education access', 'School stability, transportation, access for vulnerable students.'),
 ('iss-emergency','Emergency & disaster response', 'Disaster relief, emergency displacement, crisis mobilization.');

INSERT INTO dim_places (place_id, canonical_name, state, level, latitude, longitude) VALUES
 ('plc-ny',        'New York',      'NY', 'state',   42.75,    -75.5),
 ('plc-nyc',       'New York City', 'NY', 'city',    40.7128,  -74.006),
 ('plc-buffalo',   'Buffalo',       'NY', 'city',    42.8864,  -78.8784),
 ('plc-ca',        'California',    'CA', 'state',   36.8,     -119.4),
 ('plc-sd',        'San Diego',     'CA', 'county',  32.7157,  -117.1611),
 ('plc-la',        'Los Angeles',   'CA', 'county',  34.0522,  -118.2437),
 ('plc-va',        'Virginia',      'VA', 'state',   37.8,     -78.6),
 ('plc-fairfax',   'Fairfax County','VA', 'county',  38.8462,  -77.3064),
 ('plc-richmond',  'Richmond',      'VA', 'city',    37.5407,  -77.436);

INSERT INTO opportunity_cards
 (opportunity_id, title, state, place_id, place_name, issue_id, issue_label,
  relevance_direction, signal_type, event_date, confidence, priority_score, source_name) VALUES
 ('opp-ny-001','NYC foster youth face school-transportation gaps','NY','plc-nyc','New York City','iss-foster','Family preservation & foster care','opportunity','report_indicator','2026-06-22',0.82,88,'Advocates for Children of NY'),
 ('opp-ny-002','NY committee weighs new mandatory-reporting expansion','NY','plc-ny','New York','iss-childwel','Child welfare & protection','risk','proposed_mandate','2026-07-30',0.74,84,'NY State Senate'),
 ('opp-ny-003','Buffalo youth mental-health crisis funding advances','NY','plc-buffalo','Buffalo','iss-youthmh','Youth mental health','opportunity','funding','2026-05-14',0.7,73,'Buffalo News'),
 ('opp-ny-004','NY eviction filings climb in outer boroughs','NY','plc-nyc','New York City','iss-housing','Housing stability & homelessness','watch','report_indicator','2026-04-02',0.61,58,'Office of Court Administration'),
 ('opp-ca-001','California K-12 homelessness hits record high','CA','plc-ca','California','iss-housing','Housing stability & homelessness','risk','report_indicator','2026-08-27',0.86,91,'CalMatters'),
 ('opp-ca-002','San Diego expands kinship-care navigator program','CA','plc-sd','San Diego','iss-foster','Family preservation & foster care','opportunity','program','2026-07-11',0.78,80,'County of San Diego'),
 ('opp-ca-003','LA County disaster displacement strains shelters','CA','plc-la','Los Angeles','iss-emergency','Emergency & disaster response','risk','emergency','2026-08-19',0.75,79,'LA County OEM'),
 ('opp-ca-004','CA bill would boost foster-family tax relief','CA','plc-ca','California','iss-poverty','Poverty & economic support','opportunity','bill_introduced','2026-06-05',0.72,76,'California Legislature'),
 ('opp-va-001','Virginia hearing debates new CPS reporting rules','VA','plc-richmond','Richmond','iss-childwel','Child welfare & protection','risk','committee_hearing','2026-07-16',0.77,82,'Virginia LIS'),
 ('opp-va-002','Fairfax launches food & material-needs coalition','VA','plc-fairfax','Fairfax County','iss-food','Food & material needs','opportunity','program','2026-06-28',0.69,71,'Fairfax County Gov'),
 ('opp-va-003','Virginia foster-care caseloads rise statewide','VA','plc-va','Virginia','iss-foster','Family preservation & foster care','watch','report_indicator','2026-05-20',0.64,60,'VA Dept of Social Services'),
 ('opp-va-004','VA proposes school-stability transport for foster kids','VA','plc-va','Virginia','iss-edu','Education access','opportunity','bill_introduced','2026-08-01',0.73,77,'Virginia Mercury');

INSERT INTO opportunity_details
 (opportunity_id, summary, why_it_matters, recommended_action, affected_populations, source_type,
  impact_magnitude, timing_urgency, locality, evidence_confidence) VALUES
 ('opp-ny-001','A new report finds 6,650+ NYC students in foster care face stark disparities in school stability and timely transportation.','Concrete, addressable barriers (transportation, school stability) are exactly where CarePortal community responders can meet needs — a strong recruiting hook for NYC churches and partners.','Reach out to NYC-area faith partners with the transportation-gap data; frame a CarePortal responder drive around foster youth school stability.',ARRAY['foster youth','K-12 students'],'nonprofit report',0.85,0.7,0.9,0.82),
 ('opp-ny-002','A state committee is weighing an expansion of mandatory-reporting requirements that could increase reporting burden on community partners.','New reporting mandates could adversely affect how CarePortal partners operate; GO can offer amended language and mobilize local voices before markup.','Brief affected State Directors; prepare a one-page position and identify partners to testify or submit comment.',ARRAY['mandated reporters','community organizations'],'legislation',0.8,0.85,0.75,0.74),
 ('opp-ny-003','Buffalo-area youth mental-health crisis services are set to receive expanded funding this cycle.','Expanded crisis services create partnership openings for CarePortal to connect families to newly funded resources.','Map the funded providers and introduce CarePortal as a referral/response channel to local partners.',ARRAY['adolescents','families in crisis'],'news',0.6,0.6,0.7,0.7),
 ('opp-ny-004','Eviction filings are rising in NYC outer boroughs, an early indicator of housing instability.','Rising instability signals growing concrete needs CarePortal responders can help meet; useful context for outreach even if not yet actionable.','Monitor; add to the NYC housing watch list and revisit if filings keep climbing.',ARRAY['low-income families','renters'],'government data',0.55,0.4,0.7,0.61),
 ('opp-ca-001','Nearly 300,000 California K-12 students experienced homelessness in 2024-25, the highest on record and up 10% from the prior peak.','A record surge in student homelessness is both a serious risk to families and a clear call to expand CarePortal partner capacity across the state.','Lead statewide outreach with the record-high figure; prioritize counties with the sharpest increases for partner recruitment.',ARRAY['K-12 students','homeless youth','low-income families'],'news',0.95,0.8,0.85,0.86),
 ('opp-ca-002','San Diego County is expanding a kinship-care navigator program to support relatives raising children.','Program expansion creates a concrete partnership and referral opportunity for CarePortal in San Diego.','Contact the county program lead; propose CarePortal as a community-response layer for navigator referrals.',ARRAY['kinship caregivers','foster children'],'government',0.7,0.65,0.9,0.78),
 ('opp-ca-003','Recent disaster displacement in LA County is straining shelter capacity and emergency services.','Emergency displacement drives urgent material needs — a moment for CarePortal to activate responders quickly.','Activate LA-area partners for rapid response; surface the most urgent shelter/material gaps.',ARRAY['displaced families','disaster survivors'],'government',0.8,0.95,0.85,0.75),
 ('opp-ca-004','A new bill would increase tax relief for foster families in California.','Improved economic support strengthens foster-family recruitment and retention — core to GO''s mission.','Track the bill; prepare supportive talking points and identify foster-parent voices to amplify.',ARRAY['foster families'],'legislation',0.7,0.6,0.8,0.72),
 ('opp-va-001','A Virginia committee hearing is debating new child-protective-services reporting rules.','Proposed rules could raise the compliance burden on CarePortal partners; GO can engage early with amended language.','Assign a State Director to attend/track the hearing; draft an amendment suggestion and a partner call list.',ARRAY['mandated reporters','families'],'legislation',0.78,0.85,0.8,0.77),
 ('opp-va-002','Fairfax County is launching a coalition focused on food and material-needs response.','A new coalition is a ready-made partnership channel for CarePortal in Northern Virginia.','Join the coalition kickoff; position CarePortal as the real-time needs-response tool for members.',ARRAY['low-income families','children'],'government',0.65,0.6,0.9,0.69),
 ('opp-va-003','Foster-care caseloads are rising across Virginia, per the state social-services report.','Rising caseloads indicate growing need and future recruiting priority for CarePortal partners.','Add to the VA watch list; use trend in statewide partnership pitch decks.',ARRAY['foster children','caseworkers'],'government data',0.6,0.45,0.75,0.64),
 ('opp-va-004','A Virginia bill proposes guaranteed school-stability transportation for children in foster care.','School-stability transport is a concrete need CarePortal responders can support — and an advocacy win to amplify.','Prepare supportive outreach to VA partners; connect the bill to CarePortal''s school-stability response stories.',ARRAY['foster youth','K-12 students'],'legislation',0.72,0.7,0.8,0.73);

INSERT INTO opportunity_citations
 (citation_id, opportunity_id, quote, source_name, source_url, char_start, char_end, retrieved_at, is_primary) VALUES
 ('cit-ny-001a','opp-ny-001','Data on the 6,650 students in foster care last year show stark disparities and the critical importance of school stability for this population.','Advocates for Children of NY','https://www.advocatesforchildren.org/','120','245','2026-06-23',TRUE),
 ('cit-ny-002a','opp-ny-002','The committee will consider expanding the categories of professionals required to report suspected abuse or neglect.','NY State Senate','https://www.nysenate.gov/legislation','40','150','2026-07-31',TRUE),
 ('cit-ny-003a','opp-ny-003','The funding package expands crisis and school-based mental-health services for adolescents in the region.','Buffalo News','https://buffalonews.com/','10','120','2026-05-15',TRUE),
 ('cit-ny-004a','opp-ny-004','Eviction filings in the outer boroughs have risen steadily over the past two quarters.','Office of Court Administration','https://ww2.nycourts.gov/','5','95','2026-04-03',TRUE),
 ('cit-ca-001a','opp-ca-001','Nearly 300,000 California K-12 students experienced homelessness in the 2024-25 school year, the highest numbers ever recorded.','CalMatters','https://calmatters.org/','0','130','2026-08-27',TRUE),
 ('cit-ca-002a','opp-ca-002','The county is expanding its kinship navigator program to help relative caregivers access support and services.','County of San Diego','https://www.sandiegocounty.gov/','15','140','2026-07-12',TRUE),
 ('cit-ca-003a','opp-ca-003','Emergency shelters are near capacity as displacement from the recent disaster continues.','LA County OEM','https://ceo.lacounty.gov/emergency-management/','8','110','2026-08-20',TRUE),
 ('cit-ca-004a','opp-ca-004','The bill would expand tax relief available to qualified foster families in the state.','California Legislature','https://leginfo.legislature.ca.gov/','12','105','2026-06-06',TRUE),
 ('cit-va-001a','opp-va-001','The hearing will address proposed changes to reporting requirements and expectations for professionals.','Virginia LIS','https://lis.virginia.gov/','20','130','2026-07-17',TRUE),
 ('cit-va-002a','opp-va-002','The county announced a new coalition to coordinate food and material-needs response for families.','Fairfax County Gov','https://www.fairfaxcounty.gov/','10','120','2026-06-29',TRUE),
 ('cit-va-003a','opp-va-003','The annual report shows foster-care caseloads rising across the commonwealth.','VA Dept of Social Services','https://www.dss.virginia.gov/','5','95','2026-05-21',TRUE),
 ('cit-va-004a','opp-va-004','The bill proposes guaranteed transportation to maintain school stability for children in foster care.','Virginia Mercury','https://www.virginiamercury.com/','15','135','2026-08-02',TRUE);

-- Read access for the app service principal (and everyone): USAGE on the schema
-- + SELECT on all current and future tables.
GRANT USAGE ON SCHEMA gold TO PUBLIC;
GRANT SELECT ON ALL TABLES IN SCHEMA gold TO PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA gold GRANT SELECT ON TABLES TO PUBLIC;
