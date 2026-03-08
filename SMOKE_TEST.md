# Smoke Test Checklist -- Post-Deploy Verification

Run this checklist after deploying to Railway (or any cloud environment).

## Prerequisites
- [ ] Railway deployment shows "Active" status
- [ ] Railway URL is accessible (*.up.railway.app)

## Authentication
- [ ] Visiting the URL shows the password prompt (auth gate)
- [ ] Entering wrong password shows error
- [ ] Entering correct APP_PASSWORD grants access

## Navigation
- [ ] Companies page loads
- [ ] Enrich page loads
- [ ] Emails page loads
- [ ] Analytics page loads
- [ ] Settings page loads

## Settings
- [ ] Settings page shows API key validation status for configured providers
- [ ] Salesforce connection test works (if credentials configured)

## Core Functionality
- [ ] Can import a CSV of companies on the Companies page
- [ ] Can manually add a company
- [ ] Enrichment page shows uploaded campaign data
- [ ] Email generation page shows completed campaigns

## Data Persistence
- [ ] After navigating away and back, previously imported data is still present
- [ ] After Railway redeploy, data persists (volume mount working)

## Health
- [ ] `curl https://<railway-url>/_stcore/health` returns "ok"
