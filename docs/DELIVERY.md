# Delivery feasibility

Delivery feasibility is determined only from the supplier's declared delivery capability and the client's required timeline. Location is stored and used in matching as a separate business factor. Geographical distance and road-routing time are not used to infer actual delivery time.

## Authoritative check

When both values parse as a number of days:

- Client required delivery = X days
- Supplier declared delivery = Y days

If Y ≤ X, the supplier passes the delivery-time requirement.

If Y > X, the supplier fails the delivery-time hard filter and is not stored as an eligible match.

Unparseable timelines do not auto-fail the pair.

## Location

Client and supplier location fields remain on requirements, offerings, dashboards, and match explanations. Location compatibility (token overlap) is a structured matching feature and can appear as “Location compatible”. Location is **not** converted into a transit-time estimate.

## Ranking

Unchanged. `semantic_score`, `ml_score`, and `final_score` come from the existing ML matching pipeline. Declared delivery is a hard filter before scoring; it is not mixed into the classifier as a Google/route input.
