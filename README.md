# Wave Accounting MCP Server

A Model Context Protocol (MCP) server that integrates Claude with Wave Accounting to automate expense tracking and income transaction creation.

## Features

- 📸 **Expense Creation from Receipts**: Automatically extract and create expenses from receipt text
- 💰 **Income Transaction Creation**: Create income transactions from payment data
- 🏢 **Multi-Business Support**: Manage multiple Wave businesses seamlessly
- 🔍 **Vendor & Customer Search**: Find existing vendors and customers
- 📊 **Account Management**: List and categorize transactions with proper accounts
- 🔄 **Real-time Integration**: Direct connection to Wave's GraphQL API

## Prerequisites

- Python 3.8 or higher
- Wave Business account with API access
- Claude Desktop application
- A Wave Developer App (Client ID + Client Secret) and a Full Access Token (access + refresh token pair)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/vinnividivicci/wave_mcp.git
cd wave_mcp
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file with your Wave Developer App credentials:
```env
WAVE_CLIENT_ID=your_wave_client_id
WAVE_CLIENT_SECRET=your_wave_client_secret
```

4. Run the one-time OAuth bootstrap to obtain and persist access + refresh tokens:
```bash
python mcp_server.py --auth
```

This opens your browser to Wave's authorization page, captures the callback on
`http://localhost:8765/callback`, exchanges the code for tokens, and writes both
`WAVE_ACCESS_TOKEN` and `WAVE_REFRESH_TOKEN` into your `.env`.

> **Important**: Before running `--auth`, register `http://localhost:8765/callback`
> as a redirect URI in your Wave Developer App. To use a different port or path,
> register it in Wave first and pass it via `--redirect-uri`.

After bootstrap, the server will silently refresh the access token whenever Wave
returns 401, persisting the rotated tokens back to `.env` so they survive restarts.
You should never need to touch `WAVE_ACCESS_TOKEN` again.

## Getting Your Wave Credentials

1. Sign in to the [Wave Developer Portal](https://developer.waveapps.com/) and create an application — you'll get a **Client ID** and **Client Secret**.
2. In your application's settings, register `http://localhost:8765/callback` as an authorized redirect URI.
3. Run `python mcp_server.py --auth` to mint your access + refresh tokens (see above).
4. Reference docs:
   - [OAuth Guide](https://developer.waveapps.com/hc/en-us/articles/360019493652-OAuth-Guide)
   - [OAuth Scopes](https://developer.waveapps.com/hc/en-us/articles/360032818132-OAuth-Scopes)
   - [API Documentation](https://developer.waveapps.com/hc/en-us/categories/360001114072-Documentation)

> **Note**: Wave API access may require approval. Check Wave's current developer program status.

## Configuration

### Claude Desktop Setup

Add the server to your Claude Desktop configuration:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "wave-accounting": {
      "command": "python",
      "args": ["/absolute/path/to/wave_mcp/mcp_server.py"],
      "env": {
        "WAVE_CLIENT_ID": "your_wave_client_id",
        "WAVE_CLIENT_SECRET": "your_wave_client_secret",
        "WAVE_ACCESS_TOKEN": "your_wave_access_token",
        "WAVE_REFRESH_TOKEN": "your_wave_refresh_token"
      }
    }
  }
}
```

Restart Claude Desktop after saving the configuration.

## Usage Examples

### Creating an Expense from a Receipt

```
I have a receipt from Office Depot for $45.99 dated March 15, 2024. 
It's for office supplies - printer paper and pens.
```

### Creating Income from Payment

```
Received payment of $1,500 from ABC Company on March 20, 2024 
for consulting services invoice #1234.
```

### Listing Available Accounts

```
Show me my expense accounts in Wave.
```

### Setting Active Business (Multi-Business Accounts)

```
List my Wave businesses and set the active one.
```

## Available MCP Tools

The server exposes **74 tools** covering ~100% of Wave's public GraphQL API write surface,
plus comprehensive read tools. Tools are organized by domain:

### Reference & lookup
`get_current_user`, `get_oauth_application`, `list_currencies`, `get_currency`,
`list_countries`, `get_country`, `get_province`

### Businesses
`list_businesses`, `get_business`, `set_business`

### Chart of Accounts
`list_accounts`, `get_account`, `create_account`, `patch_account`, `archive_account`,
`list_account_types`, `list_account_subtypes`

### Customers
`list_customers`, `get_customer`, `create_customer`, `patch_customer`, `delete_customer`

### Vendors *(read-only — Wave does not expose vendor mutations)*
`list_vendors`, `get_vendor`

### Products & services
`list_products`, `get_product`, `create_product`, `patch_product`, `archive_product`

### Sales taxes
`list_sales_taxes`, `get_sales_tax`, `create_sales_tax`, `patch_sales_tax`, `archive_sales_tax`

### Money transactions
- `create_money_transaction` — general-purpose (works for expenses, income, transfers, journal entries)
- `create_transfer` — between two of your own accounts
- `create_journal_entry` — alias for create_money_transaction (Equity/COGS friendly)
- `create_transactions_bulk` — push many transactions in one call (great for bank statement imports)

### Invoices
`list_invoices`, `get_invoice`, `create_invoice`, `patch_invoice`, `clone_invoice`,
`delete_invoice`, `approve_invoice`, `mark_invoice_sent`, `send_invoice`,
`record_invoice_payment`, `patch_invoice_payment`, `delete_invoice_payment`,
`send_invoice_payment_receipt`, `get_invoice_payment`, `get_invoice_estimate_settings`

### Estimates
`list_estimates`, `get_estimate`, `create_estimate`, `patch_estimate`, `clone_estimate`,
`delete_estimate`, `approve_estimate`, `send_estimate`, `mark_estimate_sent`,
`mark_estimate_accepted`, `reset_estimate_acceptance`, `generate_estimate_pdf`,
`send_estimate_acceptance_email`, `convert_estimate_to_invoice`,
`delete_estimate_payment`, `send_estimate_deposit_receipt`

### Legacy / convenience
`create_expense_from_receipt`, `create_income_from_payment` (free-text categories with
fuzzy matching — prefer the precise `create_money_transaction` for new code),
`search_customer`, `search_vendor`, `debug_accounts`

## Inherent gaps (Wave's public API does not expose these)
- Vendor creation/edit/delete — must be done in the web UI
- Reading the money transaction ledger — only writes are exposed
- Attaching receipt images/PDFs to transactions
- Bank-feed import API

## Important Notes

### Quirks
- **`create_product`**: Wave's schema marks `incomeAccountId` and `expenseAccountId` as
  optional, but the API rejects products that don't supply at least one. Pass both to
  create a product that's both sold and bought.
- **`patch_estimate`**: EstimatePatchInput requires several fields even when patching
  (customerId, status, title, estimateDate, currency, exchangeRate, dueDate). Pass the
  current values to leave them unchanged.
- **Rate limit**: Wave allows ~2 concurrent requests; the server enforces this with a
  semaphore inside `WaveClient`.

### Token TTL
- OAuth access tokens expire (~1 week). Provide `WAVE_CLIENT_ID`, `WAVE_CLIENT_SECRET`,
  and `WAVE_REFRESH_TOKEN` so the server refreshes them automatically and writes the
  rotated values back to `.env`.

## Development

### Running smoke tests
```bash
# Read-only smoke (safe — touches no data)
python tests/smoke.py

# Full smoke including create→patch→archive round-trip (creates and cleans up test
# records). Strongly recommend pointing at a sandbox/empty business:
python tests/smoke.py --business-id <BUSINESS_ID> --write
```

### Project Structure
```
wave_mcp/
├── mcp_server.py             # Entry point (MCP wiring + dispatch)
├── wave_client.py            # WaveClient: GraphQL + OAuth refresh + rate limit
├── oauth.py                  # --auth bootstrap flow
├── errors.py                 # Standardized error formatting
├── fuzzy.py                  # Legacy fuzzy account-name matcher
├── wave_schema.json          # Cached schema introspection (reference only)
├── tools/
│   ├── __init__.py           # Aggregates every tool() generator
│   ├── _common.py            # Shared helpers (need_business, json_text, …)
│   ├── reference.py          # currencies/countries/user/oauth_app
│   ├── businesses.py
│   ├── accounts.py
│   ├── customers.py
│   ├── vendors.py
│   ├── products.py
│   ├── sales_taxes.py
│   ├── transactions.py       # money transactions (single + bulk + transfer + journal)
│   ├── invoices.py           # full invoice + invoice-payment lifecycle
│   ├── estimates.py          # full estimate lifecycle
│   └── legacy.py             # create_expense_from_receipt and friends
├── tests/
│   └── smoke.py              # End-to-end smoke (read + optional write)
├── requirements.txt
├── README.md
├── LICENSE
└── .env                      # Your credentials (not tracked)
```

## Troubleshooting

### "Wave client not initialized"
- Verify your `WAVE_ACCESS_TOKEN` is set correctly
- Check that the token has valid permissions

### "No business selected"
- Use the `list_businesses` tool to see available businesses
- Set the active business with `set_business`

### MCP Server Not Available in Claude
- Ensure the path in `claude_desktop_config.json` is absolute
- Verify Python and all dependencies are installed
- Restart Claude Desktop

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built for use with [Claude Desktop](https://claude.ai)
- Integrates with [Wave Accounting](https://www.waveapps.com)
- Uses the [Model Context Protocol](https://modelcontextprotocol.io)

## Security

- Never commit your `.env` file or API keys
- Use environment variables for all sensitive data
- Regularly rotate your API tokens
- Follow Wave's security best practices
