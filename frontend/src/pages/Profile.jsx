import { useEffect, useState } from "react";
import Layout from "../components/Layout";
import { useAuth } from "../AuthContext";
import { ApiError } from "../api";
import { profileInitials } from "../profileDisplay";

export default function Profile() {
  const { user, updateProfile, uploadPhoto } = useAuth();
  const [form, setForm] = useState({
    full_name: user.full_name,
    company_name: user.company_name || "",
    phone: user.phone || "",
  });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [photoBusy, setPhotoBusy] = useState(false);

  useEffect(() => {
    setForm({
      full_name: user.full_name,
      company_name: user.company_name || "",
      phone: user.phone || "",
    });
  }, [user]);

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function handlePhoto(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setError("");
    setSuccess("");
    setPhotoBusy(true);
    try {
      await uploadPhoto(file);
      setSuccess("Profile photo updated.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to upload photo");
    } finally {
      setPhotoBusy(false);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setSubmitting(true);
    try {
      await updateProfile({
        full_name: form.full_name,
        company_name: form.company_name,
        phone: form.phone,
      });
      setSuccess("Profile updated.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to update profile");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Layout>
      <section className="profile-edit">
        <div className="auth-panel">
          <p className="eyebrow">Details</p>
          <h2 className="page-title">Update profile.</h2>
          {error && <p className="banner banner-error">{error}</p>}
          {success && <p className="banner banner-success">{success}</p>}
          <form className="stack-form" onSubmit={handleSubmit}>
            <label className="profile-photo-field">
              Profile photo
              <div className="profile-photo-row">
                <span className="profile-photo-preview" aria-hidden="true">
                  {user.profile_photo_url ? (
                    <img src={user.profile_photo_url} alt="" />
                  ) : (
                    profileInitials(user.full_name)
                  )}
                </span>
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={handlePhoto}
                  disabled={photoBusy}
                />
              </div>
            </label>
            <label>
              Full name
              <input
                value={form.full_name}
                onChange={(event) => update("full_name", event.target.value)}
                required
              />
            </label>
            <label>
              Company name
              <input
                value={form.company_name}
                onChange={(event) => update("company_name", event.target.value)}
                required={user.role !== "ADMIN"}
              />
            </label>
            <label>
              Email
              <input value={user.email} readOnly />
            </label>
            <label>
              Phone
              <input value={form.phone} onChange={(event) => update("phone", event.target.value)} />
            </label>
            <button className="btn" type="submit" disabled={submitting}>
              {submitting ? "Saving…" : "Save changes →"}
            </button>
          </form>
        </div>
      </section>
    </Layout>
  );
}
