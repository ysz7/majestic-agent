import { useState, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { profilesApi } from "@shared/api/client";
import { Button } from "@shared/ui-kit";
import { X } from "lucide-react";
import { EnvEditor } from "./EnvEditor";

interface Props {
  profile?: string;
  onClose:  () => void;
}

type FormData = {
  profile:  string;
  name:     string;
  role:     string;
  tone:     string;
  language: string;
  port:     string;
};

function Field({
  label,
  value,
  onChange,
  disabled,
}: {
  label:     string;
  value:     string;
  onChange:  (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-col gap-[5px]">
      <label className="text-2xs text-text-muted-3 uppercase tracking-[1.2px] font-semibold">
        {label}
      </label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="border border-border rounded-control bg-bg-surface text-base text-text-sub px-[11px] py-[9px] focus:outline-none focus:border-border-strong disabled:opacity-40 w-full"
      />
    </div>
  );
}

type FormTab = "persona" | "env";

export function ProfileForm({ profile, onClose }: Props) {
  const qc    = useQueryClient();
  const isEdit = !!profile;
  const [formTab, setFormTab] = useState<FormTab>("persona");

  const [form, setForm] = useState<FormData>({
    profile:  profile ?? "",
    name:     "",
    role:     "General purpose AI assistant",
    tone:     "helpful, concise",
    language: "en",
    port:     "8000",
  });

  const { data: personaData } = useQuery({
    queryKey: ["persona", profile],
    queryFn:  () => profilesApi.getPersona(profile!),
    enabled:  isEdit,
  });

  useEffect(() => {
    if (!personaData) return;
    const d = personaData as Record<string, unknown>;
    setForm({
      profile:  profile!,
      name:     String(d.name     ?? ""),
      role:     String(d.role     ?? ""),
      tone:     String(d.tone     ?? ""),
      language: String(d.language ?? "en"),
      port:     String(d.port     ?? "8000"),
    });
  }, [personaData, profile]);

  const create = useMutation({
    mutationFn: () => profilesApi.create({ profile: form.profile, name: form.name, role: form.role }),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ["profiles"] }); onClose(); },
  });

  const update = useMutation({
    mutationFn: () =>
      profilesApi.updatePersona(profile!, {
        name:     form.name,
        role:     form.role,
        tone:     form.tone,
        language: form.language,
        port:     parseInt(form.port) || 8000,
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["profiles"] }); onClose(); },
  });

  const set = (key: keyof FormData) => (v: string) =>
    setForm((s) => ({ ...s, [key]: v }));

  const error = (create.error || update.error) as Error | null;

  return (
    <div className="flex flex-col gap-[10px]">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-[8px]">
          <span className="text-2xs text-text-muted-3 uppercase tracking-[1.2px] font-semibold">
            {isEdit ? "Edit Profile" : "New Profile"}
          </span>
          {isEdit && (
            <div className="flex items-center gap-[2px]">
              {(["persona", "env"] as FormTab[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setFormTab(t)}
                  className={`px-[9px] py-[4px] text-xs rounded-[6px] transition-colors capitalize ${
                    formTab === t
                      ? "bg-bg-selected text-text-sub border border-border-strong"
                      : "text-text-muted-2 hover:text-text-sub"
                  }`}
                >
                  {t === "env" ? ".env" : t}
                </button>
              ))}
            </div>
          )}
        </div>
        <button onClick={onClose} className="text-text-muted-2 hover:text-text-sub">
          <X size={13} />
        </button>
      </div>

      {/* Persona tab (always shown for create, conditional for edit) */}
      {(!isEdit || formTab === "persona") && (
        <>
          {!isEdit && <Field label="ID (e.g. my_agent)" value={form.profile} onChange={set("profile")} />}
          <Field label="Name"     value={form.name}     onChange={set("name")}     />
          <Field label="Role"     value={form.role}     onChange={set("role")}     />
          <Field label="Tone"     value={form.tone}     onChange={set("tone")}     />
          <Field label="Language" value={form.language} onChange={set("language")} />
          <Field label="Port"     value={form.port}     onChange={set("port")}     />

          {error && <div className="text-xs text-red-400">{error.message}</div>}

          <div className="flex justify-end gap-[7px] mt-[4px]">
            <Button variant="default" size="sm" onClick={onClose}>Cancel</Button>
            <Button
              variant="cta"
              size="sm"
              onClick={() => (isEdit ? update.mutate() : create.mutate())}
              disabled={create.isPending || update.isPending}
            >
              {isEdit ? "Save" : "Create"}
            </Button>
          </div>
        </>
      )}

      {/* .env tab (edit mode only) */}
      {isEdit && formTab === "env" && profile && (
        <EnvEditor profile={profile} />
      )}
    </div>
  );
}
