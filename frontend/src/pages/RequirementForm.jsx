import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import Layout from "../components/Layout";
import { useAuth } from "../AuthContext";
import {
  ApiError,
  createRequirement,
  getCategories,
  getRequirement,
  updateRequirement,
  uploadDocument,
} from "../api";
import "./RequirementForm.css";

const CURRENCIES = ["INR", "USD", "EUR", "GBP", "AED"];

const EMPTY = {
  company_name: "",
  product_requirement: "",
  category_id: "",
  custom_category: "",
  quantity: "",
  quantity_unit: "",
  budget: "",
  budget_currency: "",
  budget_basis: "TOTAL",
  location: "",
  delivery_timeline: "",
  additional_notes: "",
};

function otherId(categories) {
  const row = categories.find((item) => String(item.name).toLowerCase() === "other");
  return row ? String(row.id) : "";
}

function isOtherSelected(categories, categoryId) {
  const row = categories.find((item) => String(item.id) === String(categoryId));
  return Boolean(row && String(row.name).toLowerCase() === "other");
}

function categoryIdFromExtract(categories, extracted, currentId) {
  const extractedId = extracted.category_id != null ? String(extracted.category_id) : "";
  const listed = categories.some((item) => String(item.id) === extractedId);
  if (extractedId && listed) return extractedId;
  if (extracted.custom_category || extracted.category_label) {
    return otherId(categories) || currentId;
  }
  return extractedId || currentId;
}

export default function RequirementForm() {
  const { user } = useAuth();
  const { id } = useParams();
  const navigate = useNavigate();
  const editing = Boolean(id);
  const [categories, setCategories] = useState([]);
  const [form, setForm] = useState({ ...EMPTY, company_name: user.company_name || "" });
  const [documentId, setDocumentId] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getCategories()
      .then((items) => {
        if (cancelled) return;
        setCategories(items);
        if (editing) {
          getRequirement(id)
            .then((item) => {
              if (cancelled) return;
              const predefined = items.find((row) => row.id === item.category_id);
              const useOther = !predefined || String(predefined.name).toLowerCase() === "other";
              setForm({
                company_name: item.company_name,
                product_requirement: item.product_requirement,
                category_id: useOther ? otherId(items) : String(item.category_id),
                custom_category: useOther ? item.custom_category || item.category_name || "" : "",
                quantity: String(item.quantity),
                quantity_unit: item.quantity_unit || "",
                budget: String(item.budget),
                budget_currency: item.budget_currency || "",
                budget_basis: item.budget_basis || "TOTAL",
                location: item.location,
                delivery_timeline: item.delivery_timeline,
                additional_notes: item.additional_notes || "",
              });
            })
            .catch((err) => {
              if (!cancelled) setError(err instanceof ApiError ? err.message : "Unable to load requirement");
            });
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Unable to load categories");
      });
    return () => {
      cancelled = true;
    };
  }, [editing, id]);

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function payload(status) {
    const body = {
      company_name: form.company_name,
      product_requirement: form.product_requirement,
      category_id: Number(form.category_id),
      custom_category: isOtherSelected(categories, form.category_id) ? form.custom_category.trim() || null : null,
      quantity: Number(form.quantity),
      quantity_unit: form.quantity_unit.trim() || null,
      budget: Number(form.budget),
      budget_currency: form.budget_currency || null,
      budget_basis: form.budget_basis || "TOTAL",
      location: form.location,
      delivery_timeline: form.delivery_timeline,
      additional_notes: form.additional_notes.trim() || null,
    };
    if (!editing) body.status = status;
    if (documentId) body.document_id = documentId;
    return body;
  }

  async function handleUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setError("");
    setNotice("");
    try {
      const result = await uploadDocument(file);
      setDocumentId(result.id);
      const extracted = result.extracted || {};
      setForm((current) => ({
        ...current,
        company_name: extracted.company_name || current.company_name,
        product_requirement: extracted.product || extracted.product_requirement || current.product_requirement,
        category_id: categoryIdFromExtract(categories, extracted, current.category_id),
        custom_category: extracted.custom_category || extracted.category_label || current.custom_category,
        quantity: extracted.quantity != null ? String(extracted.quantity) : current.quantity,
        quantity_unit: extracted.quantity_unit || current.quantity_unit,
        budget: extracted.budget_amount != null ? String(extracted.budget_amount) : extracted.budget != null ? String(extracted.budget) : current.budget,
        budget_currency: extracted.budget_currency || current.budget_currency,
        budget_basis: extracted.budget_basis || current.budget_basis,
        location: extracted.location || current.location,
        delivery_timeline: extracted.delivery_timeline || current.delivery_timeline,
        additional_notes: extracted.additional_notes || current.additional_notes,
      }));
      setNotice("Review the extracted fields, correct anything that looks wrong, then save.");
    } catch (err) {
      setDocumentId(null);
      setError(err instanceof ApiError ? err.message : "Unable to process the document");
    }
  }

  async function save(status) {
    setError("");
    if (isOtherSelected(categories, form.category_id) && !form.custom_category.trim()) {
      setError("Enter a custom category when Other is selected.");
      return;
    }
    setSubmitting(true);
    try {
      if (editing) {
        await updateRequirement(id, payload());
        navigate(`/requirements/${id}`);
      } else {
        const created = await createRequirement(payload(status));
        navigate(`/requirements/${created.id}`);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to save requirement");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Layout>
      <section className="requirement-form-page">
        <div className="requirement-form-page__intro">
          <p className="eyebrow">Client requirement</p>
          <h1>{editing ? "Edit requirement." : "New requirement."}</h1>
          <p className="lede">
            Enter the requirement manually. Uploading a document is optional and never saved until you confirm.
          </p>
          {error && <p className="banner banner-error">{error}</p>}
          {notice && <p className="banner banner-success">{notice}</p>}
        </div>
        <form
          className="stack-form compact-form requirement-form-page__body"
          onSubmit={(event) => {
            event.preventDefault();
            save(editing ? undefined : "SUBMITTED");
          }}
        >
          <div className="requirement-form-page__media">
            {!editing && (
              <label>
                Optional document
                <input type="file" accept=".pdf,.docx,.txt,application/pdf,.txt" onChange={handleUpload} />
              </label>
            )}
            <p className="lede">
              Upload a PDF, Word, or text file on the left if you have one. Review the extracted fields on the right,
              then save once.
            </p>
          </div>
          <div className="requirement-form-page__fields">
            <div className="form-grid">
              <label>
                Company / client name
                <input value={form.company_name} onChange={(event) => update("company_name", event.target.value)} required />
              </label>
              <label>
                Category
                <select value={form.category_id} onChange={(event) => update("category_id", event.target.value)} required>
                  <option value="">Select a category</option>
                  {categories.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
              {isOtherSelected(categories, form.category_id) && (
                <label>
                  Custom category
                  <input
                    value={form.custom_category}
                    onChange={(event) => update("custom_category", event.target.value)}
                    placeholder="e.g. Renewable Energy Equipment"
                    required
                  />
                </label>
              )}
              <label>
                Product requirement
                <input
                  value={form.product_requirement}
                  onChange={(event) => update("product_requirement", event.target.value)}
                  required
                />
              </label>
              <label>
                Quantity required
                <input
                  type="number"
                  min="1"
                  value={form.quantity}
                  onChange={(event) => update("quantity", event.target.value)}
                  required
                />
              </label>
              <label>
                Quantity unit
                <input value={form.quantity_unit} onChange={(event) => update("quantity_unit", event.target.value)} />
              </label>
              <label>
                Budget amount
                <input
                  type="number"
                  min="0"
                  value={form.budget}
                  onChange={(event) => update("budget", event.target.value)}
                  required
                />
              </label>
              <label>
                Currency
                <select value={form.budget_currency} onChange={(event) => update("budget_currency", event.target.value)}>
                  <option value="">Unknown</option>
                  {CURRENCIES.map((code) => (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Budget basis
                <select value={form.budget_basis} onChange={(event) => update("budget_basis", event.target.value)}>
                  <option value="TOTAL">Total budget</option>
                  <option value="PER_UNIT">Per unit budget</option>
                </select>
              </label>
              <label>
                Location
                <input value={form.location} onChange={(event) => update("location", event.target.value)} required />
              </label>
              <label>
                Delivery timeline
                <input
                  value={form.delivery_timeline}
                  onChange={(event) => update("delivery_timeline", event.target.value)}
                  required
                />
              </label>
              <label className="span-2">
                Additional notes
                <textarea
                  maxLength={2000}
                  rows={2}
                  value={form.additional_notes}
                  onChange={(event) => update("additional_notes", event.target.value)}
                />
              </label>
            </div>
            <div className="actions-row">
              {!editing && (
                <button className="btn btn-ghost" type="button" disabled={submitting} onClick={() => save("DRAFT")}>
                  Save draft
                </button>
              )}
              <button className="btn" type="submit" disabled={submitting}>
                {submitting ? "Saving…" : editing ? "Save changes →" : "Submit requirement →"}
              </button>
            </div>
            <p className="form-foot">
              <Link to={editing ? `/requirements/${id}` : "/dashboard"}>Back</Link>
            </p>
          </div>
        </form>
      </section>
    </Layout>
  );
}
