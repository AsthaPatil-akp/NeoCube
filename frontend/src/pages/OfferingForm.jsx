import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import Layout from "../components/Layout";
import { useAuth } from "../AuthContext";
import {
  ApiError,
  createOffering,
  deleteOfferingProductImage,
  extractOfferingProductImages,
  extractSupplierDocumentImages,
  getCategories,
  getOffering,
  selectOfferingProductImage,
  updateOffering,
  uploadOfferingProductImage,
  uploadSupplierDocument,
} from "../api";
import { isAllowedProductImage } from "../aiProductFinder";
import "./OfferingForm.css";

const CURRENCIES = ["INR", "USD", "EUR", "GBP", "AED"];

const EMPTY = {
  supplier_name: "",
  product_offered: "",
  category_id: "",
  custom_category: "",
  available_quantity: "",
  quantity_unit: "",
  price_amount: "",
  price_currency: "",
  price_basis: "PER_UNIT",
  pricing_details: "",
  location: "",
  delivery_capability: "",
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

export default function OfferingForm() {
  const { user } = useAuth();
  const { id } = useParams();
  const navigate = useNavigate();
  const editing = Boolean(id);
  const [categories, setCategories] = useState([]);
  const [form, setForm] = useState({ ...EMPTY, supplier_name: user.company_name || "" });
  const [documentId, setDocumentId] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [hasProductImage, setHasProductImage] = useState(false);
  const [productImageUrl, setProductImageUrl] = useState("");
  const [productImageSource, setProductImageSource] = useState("");
  const [pendingProductFile, setPendingProductFile] = useState(null);
  const [pendingPreviewUrl, setPendingPreviewUrl] = useState("");
  const [imageBusy, setImageBusy] = useState(false);
  const [candidates, setCandidates] = useState([]);
  const [selectedCandidateId, setSelectedCandidateId] = useState("");
  const [candidateOfferingId, setCandidateOfferingId] = useState(null);
  const [extractMessage, setExtractMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    getCategories()
      .then((items) => {
        if (cancelled) return;
        setCategories(items);
        if (editing) {
          getOffering(id)
            .then((item) => {
              if (cancelled) return;
              const predefined = items.find((row) => row.id === item.category_id);
              const useOther = !predefined || String(predefined.name).toLowerCase() === "other";
              setForm({
                supplier_name: item.supplier_name,
                product_offered: item.product_offered,
                category_id: useOther ? otherId(items) : String(item.category_id),
                custom_category: useOther ? item.custom_category || item.category_name || "" : "",
                available_quantity: String(item.available_quantity),
                quantity_unit: item.quantity_unit || "",
                price_amount: item.price_amount != null ? String(item.price_amount) : "",
                price_currency: item.price_currency || "",
                price_basis: item.price_basis || "PER_UNIT",
                pricing_details: item.price_amount != null ? "" : item.pricing_details || "",
                location: item.location,
                delivery_capability: item.delivery_capability,
                additional_notes: item.additional_notes || "",
              });
              setHasProductImage(Boolean(item.has_product_image));
              setProductImageUrl(item.product_image_url || "");
              setProductImageSource(item.product_image_source || "");
            })
            .catch((err) => {
              if (!cancelled) setError(err instanceof ApiError ? err.message : "Unable to load offering");
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

  async function handleProductImage(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!isAllowedProductImage(file)) {
      setError("Product image must be JPG, JPEG, PNG, or WEBP (max 5 MB).");
      event.target.value = "";
      return;
    }
    setError("");
    setNotice("");
    setCandidates([]);
    setSelectedCandidateId("");
    setExtractMessage("");

    if (!editing) {
      if (pendingPreviewUrl) URL.revokeObjectURL(pendingPreviewUrl);
      setPendingProductFile(file);
      setPendingPreviewUrl(URL.createObjectURL(file));
      setNotice("Product image selected. It will upload when you save the offering.");
      event.target.value = "";
      return;
    }

    setImageBusy(true);
    try {
      const updated = await uploadOfferingProductImage(id, file);
      applyImageState(updated);
      setNotice(
        updated.product_image_indexed
          ? "Product image indexed for AI Product Finder."
          : "Product image saved. Visual indexing will work once the vision model is available.",
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to upload product image");
    } finally {
      setImageBusy(false);
      event.target.value = "";
    }
  }

  function applyImageState(updated) {
    setHasProductImage(Boolean(updated.has_product_image));
    setProductImageUrl(updated.product_image_url || "");
    setProductImageSource(updated.product_image_source || "");
    setPendingProductFile(null);
    if (pendingPreviewUrl) URL.revokeObjectURL(pendingPreviewUrl);
    setPendingPreviewUrl("");
  }

  function clearPendingProductImage() {
    if (pendingPreviewUrl) URL.revokeObjectURL(pendingPreviewUrl);
    setPendingProductFile(null);
    setPendingPreviewUrl("");
  }

  async function removeProductImage() {
    if (!editing) {
      clearPendingProductImage();
      return;
    }
    setError("");
    setImageBusy(true);
    try {
      const updated = await deleteOfferingProductImage(id);
      applyImageState(updated);
      setNotice("Product image removed.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to remove product image");
    } finally {
      setImageBusy(false);
    }
  }

  async function runDocumentImageExtraction(offeringId) {
    setImageBusy(true);
    setExtractMessage("");
    setCandidates([]);
    setSelectedCandidateId("");
    try {
      const result = await extractOfferingProductImages(offeringId);
      setCandidateOfferingId(offeringId);
      setCandidates(result.candidates || []);
      if (result.message) setExtractMessage(result.message);
      if ((result.candidates || []).length === 0) {
        setNotice(result.message || "No product image was found in this document.");
      }
      return result;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to extract images from document");
      return null;
    } finally {
      setImageBusy(false);
    }
  }

  async function useSelectedCandidate() {
    if (!candidateOfferingId || !selectedCandidateId) {
      setError("Select the image representing your product.");
      return;
    }
    setImageBusy(true);
    setError("");
    try {
      const updated = await selectOfferingProductImage(candidateOfferingId, selectedCandidateId);
      applyImageState(updated);
      setCandidates([]);
      setSelectedCandidateId("");
      setNotice("Selected document image saved as the product image.");
      if (!editing) {
        navigate(`/offerings/${candidateOfferingId}`);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to use selected image");
    } finally {
      setImageBusy(false);
    }
  }

  function update(field, value) {
    setForm((current) => {
      const next = { ...current, [field]: value };
      if (field === "price_amount" || field === "price_currency" || field === "price_basis") {
        next.pricing_details = "";
      }
      return next;
    });
  }

  function payload(status) {
    const amount = form.price_amount === "" ? null : Number(form.price_amount);
    const body = {
      supplier_name: form.supplier_name,
      product_offered: form.product_offered,
      category_id: Number(form.category_id),
      custom_category: isOtherSelected(categories, form.category_id) ? form.custom_category.trim() || null : null,
      available_quantity: Number(form.available_quantity),
      quantity_unit: form.quantity_unit.trim() || null,
      price_amount: amount,
      price_currency: form.price_currency || null,
      price_basis: form.price_basis || null,
      pricing_details: amount == null ? form.pricing_details.trim() || null : null,
      location: form.location,
      delivery_capability: form.delivery_capability,
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
      const result = await uploadSupplierDocument(file);
      setDocumentId(result.id);
      const extracted = result.extracted || {};
      setForm((current) => ({
        ...current,
        supplier_name: extracted.company_name || current.supplier_name,
        product_offered: extracted.product || extracted.product_requirement || current.product_offered,
        category_id: categoryIdFromExtract(categories, extracted, current.category_id),
        custom_category: extracted.custom_category || extracted.category_label || current.custom_category,
        available_quantity: extracted.quantity != null ? String(extracted.quantity) : current.available_quantity,
        quantity_unit: extracted.quantity_unit || current.quantity_unit,
        price_amount:
          extracted.price_amount != null
            ? String(extracted.price_amount)
            : extracted.budget_amount != null
              ? String(extracted.budget_amount)
              : current.price_amount,
        price_currency: extracted.price_currency || extracted.budget_currency || current.price_currency,
        price_basis: extracted.price_basis || extracted.budget_basis || current.price_basis,
        pricing_details: "",
        location: extracted.location || current.location,
        delivery_capability: extracted.delivery_timeline || current.delivery_capability,
        additional_notes: extracted.additional_notes || current.additional_notes,
      }));
      setNotice("Review the extracted fields, correct anything that looks wrong, then save.");
      if (!pendingProductFile) {
        try {
          const images = await extractSupplierDocumentImages(result.id);
          setCandidateOfferingId(null);
          setSelectedCandidateId("");
          setCandidates(images.candidates || []);
          setExtractMessage(images.message || "");
          if ((images.candidates || []).length > 0) {
            setNotice(
              "Select a product image on the left if you want one, then review the fields and publish once.",
            );
          } else if (images.message) {
            setNotice(`${images.message} Review the extracted fields, then save.`);
          }
        } catch {
          setCandidates([]);
        }
      }
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
    if (form.price_amount === "" && !form.pricing_details.trim()) {
      setError("Enter a price amount or pricing details.");
      return;
    }
    setSubmitting(true);
    try {
      if (editing) {
        await updateOffering(id, payload());
        navigate(`/offerings/${id}`);
      } else {
        const created = await createOffering(payload(status));
        if (pendingProductFile) {
          await uploadOfferingProductImage(created.id, pendingProductFile);
        } else if (documentId && selectedCandidateId) {
          await selectOfferingProductImage(created.id, selectedCandidateId, documentId);
        }
        navigate(`/offerings/${created.id}`);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to save offering");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Layout>
      <section className="offering-form-page">
        <div className="offering-form-page__intro">
          <p className="eyebrow">Supplier offering</p>
          <h1>{editing ? "Edit offering." : "New offering."}</h1>
          <p className="lede">
            Describe what you can supply. Uploading a document is optional and never saved until you confirm. Only
            active offerings are used for matching.
          </p>
          {error && <p className="banner banner-error">{error}</p>}
          {notice && <p className="banner banner-success">{notice}</p>}
        </div>
        <form
          className="stack-form compact-form offering-form-page__body"
          onSubmit={(event) => {
            event.preventDefault();
            save(editing ? undefined : "ACTIVE");
          }}
        >
          <div className="offering-form-page__media">
            {!editing && (
              <label>
                Optional document
                <input type="file" accept=".pdf,.docx,.txt,application/pdf,.txt" onChange={handleUpload} />
              </label>
            )}
            <label>
              Product Image (Optional)
              <input
                type="file"
                accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
                disabled={imageBusy || submitting}
                onChange={handleProductImage}
              />
            </label>
            {(pendingPreviewUrl || (hasProductImage && productImageUrl)) && (
              <div className="offering-form-page__preview">
                <img src={pendingPreviewUrl || productImageUrl} alt="Product" />
                <div>
                  {productImageSource && !pendingPreviewUrl && (
                    <p className="lede">
                      Source:{" "}
                      {productImageSource === "DOCUMENT_EXTRACTION" ? "Extracted from Document" : "Direct Upload"}
                    </p>
                  )}
                  <button className="btn btn-clear" type="button" disabled={imageBusy} onClick={removeProductImage}>
                    {pendingPreviewUrl ? "Clear selected image" : "Remove product image"}
                  </button>
                </div>
              </div>
            )}
            {editing && (
              <div className="actions-row">
                <button
                  className="btn btn-ghost"
                  type="button"
                  disabled={imageBusy}
                  onClick={() => runDocumentImageExtraction(id)}
                >
                  Extract images from linked document
                </button>
              </div>
            )}
            {candidates.length > 0 && (
              <div>
                <h3>Product Images Found</h3>
                <p className="lede">
                  {editing
                    ? "Select the image representing your product."
                    : "Select the image representing your product, then publish. You only need to publish once."}
                </p>
                <div className="offering-form-page__candidates">
                  {candidates.map((item) => (
                    <label
                      key={item.candidate_id}
                      className="offering-form-page__candidate"
                      style={{
                        outline: selectedCandidateId === item.candidate_id ? "2px solid currentColor" : undefined,
                      }}
                    >
                      <input
                        type="radio"
                        name="product-image-candidate"
                        value={item.candidate_id}
                        checked={selectedCandidateId === item.candidate_id}
                        onChange={() => setSelectedCandidateId(item.candidate_id)}
                      />
                      <img src={item.preview_url} alt={`Candidate ${item.width}×${item.height}`} />
                    </label>
                  ))}
                </div>
                {editing && (
                  <div className="actions-row">
                    <button className="btn" type="button" disabled={imageBusy || !selectedCandidateId} onClick={useSelectedCandidate}>
                      Use Selected Image
                    </button>
                  </div>
                )}
              </div>
            )}
            {extractMessage && candidates.length === 0 && <p className="banner banner-error">{extractMessage}</p>}
          </div>
          <div className="offering-form-page__fields">
            <div className="form-grid">
              <label>
                Supplier name
                <input value={form.supplier_name} onChange={(event) => update("supplier_name", event.target.value)} required />
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
                Product offered
                <input value={form.product_offered} onChange={(event) => update("product_offered", event.target.value)} required />
              </label>
              <label>
                Available quantity
                <input
                  type="number"
                  min="1"
                  value={form.available_quantity}
                  onChange={(event) => update("available_quantity", event.target.value)}
                  required
                />
              </label>
              <label>
                Quantity unit
                <input value={form.quantity_unit} onChange={(event) => update("quantity_unit", event.target.value)} />
              </label>
              <label>
                Price amount
                <input
                  type="number"
                  min="0"
                  value={form.price_amount}
                  onChange={(event) => update("price_amount", event.target.value)}
                />
              </label>
              <label>
                Currency
                <select value={form.price_currency} onChange={(event) => update("price_currency", event.target.value)}>
                  <option value="">Unknown</option>
                  {CURRENCIES.map((code) => (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Price basis
                <select value={form.price_basis} onChange={(event) => update("price_basis", event.target.value)}>
                  <option value="PER_UNIT">Per unit</option>
                  <option value="TOTAL">Total</option>
                </select>
              </label>
              <label>
                Location
                <input value={form.location} onChange={(event) => update("location", event.target.value)} required />
              </label>
              <label>
                Delivery capability
                <input
                  value={form.delivery_capability}
                  onChange={(event) => update("delivery_capability", event.target.value)}
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
                {submitting ? "Saving…" : editing ? "Save changes →" : "Publish offering →"}
              </button>
            </div>
            <p className="form-foot">
              <Link to={editing ? `/offerings/${id}` : "/supplier"}>Back</Link>
            </p>
          </div>
        </form>
      </section>
    </Layout>
  );
}
