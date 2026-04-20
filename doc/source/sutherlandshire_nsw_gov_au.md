# Sutherland Shire Council

Support for waste collection schedules provided by [Sutherland Shire Council](https://www.sutherlandshire.nsw.gov.au), NSW, Australia.

## Configuration via configuration.yaml

```yaml
waste_collection_schedule:
  sources:
    - name: sutherlandshire_nsw_gov_au
      args:
        suburb: SUBURB
        street: STREET NAME
        house_number: HOUSE NUMBER
```

### Arguments

| Argument | Description |
|----------|-------------|
| `suburb` | Your suburb in UPPER CASE, e.g. `BONNET BAY` |
| `street` | Street name (mixed case), e.g. `Washington Drive` |
| `house_number` | Your house number, e.g. `195` |

### Example

```yaml
waste_collection_schedule:
  sources:
    - name: sutherlandshire_nsw_gov_au
      args:
        suburb: BONNET BAY
        street: Washington Drive
        house_number: "195"
```

## How to find your arguments

1. Visit the [Sutherland Shire bin day lookup page](https://www.sutherlandshire.nsw.gov.au/living-here/waste-and-recycling/waste-information-booklet)
2. Select your **suburb** from the dropdown — use exactly this value for `suburb` (in UPPER CASE)
3. Select your **street** from the dropdown — use exactly this value for `street`
4. Select your **house number** — use exactly this value for `house_number`

## Notes

- **Garbage** (red lid): collected weekly
- **Recycling** (yellow lid): collected fortnightly
- **Garden Waste** (green lid): collected fortnightly, alternating with Recycling

The fortnightly schedule is determined automatically from your collection zone (derived from the Waste Information Booklet PDF link returned by the council website).
