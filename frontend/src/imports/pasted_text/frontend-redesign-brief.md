Redesign the entire frontend UI from scratch.

The current design feels too "vibe coded", overly AI-generated, and like a generic hackathon dashboard. I want you to replace that visual direction with a mature, production-grade developer platform UI.

IMPORTANT:
This is NOT a request to add more features. The main goal is to improve the visual language, information hierarchy, spacing, typography, and overall product feel.

PRODUCT:
We are building a professional API/AI routing and resilience platform inspired by the concept of unified API gateways such as OpenRouter.

The product is for software developers and engineering teams.

It should feel like a real developer infrastructure product that could be used by an engineering team at a serious company.

==================================================
CORE DESIGN DIRECTION
==================================================

Make the UI feel:

- Professional
- Calm
- Minimal
- Precise
- Technical
- Mature
- Enterprise-grade
- Developer-focused
- Functional rather than decorative

Reference the design philosophy of products such as:
- Linear
- Vercel
- Stripe Dashboard
- GitHub
- Postman
- Datadog
- Cloudflare
- modern developer portals

DO NOT copy their layouts, branding, colors, or visual assets.

Create an original visual identity.

==================================================
VERY IMPORTANT — AVOID "VIBE CODING"
==================================================

Do NOT use:

- Excessive gradients
- Giant hero sections
- Excessive glassmorphism
- Floating glowing cards
- Neon colors
- Huge rounded cards
- Excessive shadows
- Excessive pill-shaped UI
- Decorative blobs
- Random AI illustrations
- 3D objects
- Overly futuristic cyberpunk styling
- Excessive animations
- Too many colors
- Huge headings
- Excessive whitespace that wastes screen space
- Generic "AI startup" aesthetics

The interface should look like it was designed by an experienced product designer for engineers.

Prioritize usability and information density.

==================================================
DEFAULT THEME
==================================================

LIGHT MODE MUST BE THE DEFAULT.

The first screen shown to the user must be LIGHT MODE.

Use:

- white backgrounds
- very light gray secondary surfaces
- dark navy/charcoal text
- subtle gray borders
- restrained blue accent
- subtle green/yellow/red status colors

Avoid making the interface overwhelmingly blue.

The overall appearance should be clean and almost documentation-like.

Also create a complete DARK MODE.

Dark mode should use:
- charcoal / near-black background
- slightly lighter surfaces
- subtle borders
- readable gray/white text
- same restrained accent system

DO NOT simply invert the light theme.

Both themes must look intentionally designed.

==================================================
TYPOGRAPHY
==================================================

Use Inter or a similar professional UI typeface.

Typography hierarchy should be restrained.

Avoid huge headings.

Page titles:
24–28px

Section titles:
16–20px

Body:
14–15px

Metadata:
12–13px

Use monospace typography only where technically appropriate:

- API endpoints
- request IDs
- JSON
- logs
- code
- technical identifiers

==================================================
LAYOUT
==================================================

Use a conventional professional SaaS application layout.

LEFT SIDEBAR:

Width approximately 230–250px.

Keep it simple.

Top:
Logo + product name

Navigation:

Overview
  Dashboard

Playground
  API Playground
  Models

Observability
  Requests
  Logs
  Analytics
  Provider Health

Resilience
  Policies
  Circuit Breakers
  Fault Injection

AI Engineering
  AI Copilot
  Incidents

Management
  API Keys
  Team
  Settings

Bottom:
Documentation
Help
User profile

Do not make the sidebar visually heavy.

Use subtle active-state backgrounds rather than large colorful blocks.

==================================================
TOP BAR
==================================================

Keep the top bar minimal.

Left:
- breadcrumb
- optional page context

Center/left:
- global search

Right:
- environment selector
- system health
- notifications
- theme switch
- profile

Avoid unnecessary controls.

==================================================
DASHBOARD
==================================================

Create a clean engineering dashboard.

Page title:

Overview

Subtitle:

"Monitor API traffic, provider health, and resilience."

Top-right:
- date range
- New Request

Metrics:

Total Requests
1.84M

Success Rate
98.7%

Average Latency
412 ms

Error Rate
1.3%

Make these metric cards compact.

Do NOT create giant colorful cards.

Each card should have:
- label
- value
- small trend
- subtle sparkline if useful

==================================================
MAIN DASHBOARD CONTENT
==================================================

Request Volume:

A clean professional chart.

Show:
- requests
- error rate

Use restrained colors.

Avoid overly colorful charts.

Provider Health:

Use a clean table.

Columns:

Provider
Status
Requests
Success Rate
Latency
Errors
Last Checked

Example:

OpenAI       Healthy      742.1K    99.2%    380ms
Anthropic    Healthy      521.4K    98.9%    412ms
Google       Degraded     312.6K    96.4%    1.2s
Mistral      Healthy      184.2K    99.1%    420ms

Use small status indicators.

==================================================
RECENT INCIDENTS
==================================================

Keep this compact.

Show:

Incident ID
Issue
Severity
Status
Time

Example:

INC-1042
Elevated provider latency
High
Resolved

INC-1041
Rate limit spike
Medium
Investigating

==================================================
QUICK ACTIONS
==================================================

Use simple list-style actions instead of colorful cards.

Examples:

Create API Key
Open Playground
Configure Resilience Policy
View Documentation

==================================================
API PLAYGROUND
==================================================

The API Playground should look like a professional API testing tool.

Do NOT make it look like a chatbot.

Layout:

REQUEST PANEL

Method:
POST

Endpoint:
/v1/chat/completions

Provider:
Select provider

Model:
Select model

Headers

Request Body

Use a proper JSON/code editor style area.

Primary button:
Send Request

RESPONSE PANEL

Status:
200 OK

Latency:
428 ms

Request ID:
req_8f21c9

Tabs:

Response
Headers
Timeline
Raw

Use monospace typography for JSON.

==================================================
REQUESTS
==================================================

Create a professional request explorer similar to engineering observability tools.

Search:
"Search request ID, provider, model..."

Filters:
Status
Provider
Model
Environment
Time
Latency

Table:

Request ID
Timestamp
Provider
Model
Status
Latency
Retries

Clicking a request should open a detail drawer.

==================================================
LOGS
==================================================

Create a dense structured-log interface.

Avoid colorful cards.

Use a table/console-style layout.

Columns:

Timestamp
Level
Service
Event
Request ID
Provider

Levels:
INFO
WARN
ERROR
DEBUG

Clicking a log opens structured JSON details.

==================================================
PROVIDER HEALTH
==================================================

Create a professional monitoring page.

Overall system state:

All Systems Operational

Then provider table.

Show:

Availability
Latency
Error Rate
Current State
Last Checked

Include a simple latency history chart.

==================================================
RESILIENCE POLICIES
==================================================

Create a clean configuration page.

Policies:

Timeout
Retry
Exponential Backoff
Rate Limiting
Circuit Breaker
Fallback

Use normal forms, toggles, inputs, and dropdowns.

Avoid oversized cards.

Example:

Timeout
[ 2.5 ] seconds

Maximum retries
[ 2 ]

Initial backoff
[ 500 ] ms

Circuit failure threshold
[ 5 ]

Recovery window
[ 30 ] seconds

Use small contextual explanations.

==================================================
CIRCUIT BREAKER
==================================================

Create a technical monitoring interface.

Provider A

Circuit:
CLOSED

Failure count:
1 / 5

Recovery window:
30 seconds

Last failure:
2 minutes ago

States:

CLOSED
HALF OPEN
OPEN

Make the state obvious but not visually dramatic.

==================================================
FAULT INJECTION
==================================================

Create a professional reliability testing page.

Header:

Fault Injection

Description:

"Simulate upstream failures and verify resilience behavior."

Include a clear warning:

"Fault injection is available only in non-production environments."

Controls:

Target Provider
Failure Type
Duration
Failure Rate
Artificial Latency

Failure types:

Timeout
HTTP 429
HTTP 500
HTTP 502
HTTP 503
Connection Failure
Latency

Primary button:

Inject Fault

After injection show:

Requests affected
Retries triggered
Circuit state
Fallback responses

==================================================
INCIDENTS
==================================================

Create a clean incident management interface.

Table:

Incident
Provider
Severity
Status
Started
Duration

Incident detail page:

Title
Status
Severity

Timeline

Detection
Retry attempts
Circuit opened
Fallback activated
Provider recovered

Metrics:

Affected requests
Failure rate
Peak latency
Duration

==================================================
AI COPILOT
==================================================

This is an important part of the product.

Do NOT design this as a generic ChatGPT clone.

It should look like an engineering analysis workspace.

Page title:

AI Engineering Copilot

Subtitle:

"Investigate incidents and understand API failures."

LEFT:
Incident selector / context

RIGHT:
Analysis workspace

Example:

INCIDENT ANALYSIS

Summary
Upstream provider latency increased significantly.

Evidence

P95 latency
820ms → 4.8s

Timeout rate
18%

Failed requests
73

Retries
146

Circuit state
OPEN

Likely Cause

Probable upstream service degradation.

Recommended Action

Maintain the current circuit breaker threshold.
Consider increasing timeout from 2s to 2.5s.

Confidence
87%

Show evidence and recommendations as structured sections.

The AI should feel integrated into the engineering workflow.

==================================================
API KEYS
==================================================

Create a security-focused API key management page.

Table:

Name
Environment
Created
Last Used
Status

Never display complete secrets.

Example:

sk_live_••••••••8F2A

Actions:

Copy
Rotate
Revoke

Include a small security notice.

==================================================
SETTINGS
==================================================

Create simple settings pages.

Sections:

General
Appearance
Security
Notifications
Environments
Team

Appearance:

Theme
○ Light
○ Dark
○ System

LIGHT should remain the default.

==================================================
COMPONENT DESIGN
==================================================

Create a consistent reusable component system.

Buttons:
- Primary
- Secondary
- Destructive
- Ghost

Inputs:
- Default
- Focus
- Error
- Disabled

Tables:
- Header
- Row hover
- Selected
- Empty
- Loading

Cards:
- minimal borders
- subtle elevation
- moderate radius

Status:
- Healthy
- Degraded
- Down
- Investigating
- Resolved

==================================================
SPACING
==================================================

Use a disciplined spacing system.

Prefer:
4px
8px
12px
16px
24px
32px

Do not randomly vary spacing.

==================================================
BORDERS AND SHADOWS
==================================================

Use borders more than shadows.

Cards should primarily be separated using:
- spacing
- subtle borders
- surface differences

Shadows should be very subtle.

==================================================
RESPONSIVE DESIGN
==================================================

Desktop-first.

Support:
1440px
1920px
1280px
tablet
mobile

On mobile:
- sidebar becomes drawer
- tables become horizontally scrollable or stacked cards
- controls adapt
- charts remain readable

==================================================
TECHNICAL IMPLEMENTATION TARGET
==================================================

The generated frontend must be intended for:

React
TypeScript
TSX

Use reusable components.

Avoid JavaScript-only implementations.

Suggested structure:

src/
  components/
  pages/
  layouts/
  hooks/
  types/
  utils/
  data/

Use TypeScript interfaces for:

Provider
Request
Incident
LogEntry
ResiliencePolicy
ApiKey
Metric
HealthStatus
CircuitState
AIAnalysis

==================================================
FINAL DESIGN PRINCIPLE
==================================================

The final interface should make a developer think:

"This is an actual engineering product."

NOT:

"This looks like an AI-generated hackathon dashboard."

Prioritize:
1. usability
2. information hierarchy
3. consistency
4. readability
5. engineering workflow
6. professional visual design

Keep the design restrained.

Light mode is the DEFAULT.

Dark mode is an equally polished alternative.

The final product should look credible enough that a developer could imagine using it every day.