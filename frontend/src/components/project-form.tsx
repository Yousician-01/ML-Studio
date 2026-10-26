"use client";

import { useState, type FormEvent } from "react";
import type { ProjectInput, ProjectTask } from "@/lib/api/projects";
import { taskLabel } from "@/lib/api/task-policy";
import { Alert, Button } from "./ui";

export function ProjectForm({
  initial,
  onSave,
  submitLabel,
}: {
  initial?: ProjectInput & { ml_objective?: ProjectTask };
  onSave: (input: ProjectInput & { ml_objective?: ProjectTask }) => Promise<void>;
  submitLabel: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      await onSave({
        ...(!initial ? { ml_objective: data.get("ml_objective") as ProjectTask } : {}),
        name: String(data.get("name")).trim(),
        problem_statement: String(data.get("problem_statement")).trim(),
        description: String(data.get("description")).trim() || null,
        success_context: String(data.get("success_context")).trim() || null,
      });
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Could not save Project.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="project-form">
      <fieldset disabled={busy}>
        <label>
          Project name
          <input
            name="name"
            required
            maxLength={200}
            defaultValue={initial?.name}
          />
        </label>
        <label>
          Problem statement
          <textarea
            name="problem_statement"
            required
            maxLength={10000}
            defaultValue={initial?.problem_statement}
            aria-describedby="problem-help"
          />
        </label>
        <p id="problem-help" className="muted">
          What do you want to predict? For example, whether a customer will
          churn in the next 30 days.
        </p>
        <label>
          Description <span className="muted">(optional)</span>
          <textarea
            name="description"
            maxLength={10000}
            defaultValue={initial?.description ?? ""}
          />
        </label>
        <label>
          Success context <span className="muted">(optional)</span>
          <textarea
            name="success_context"
            maxLength={10000}
            defaultValue={initial?.success_context ?? ""}
          />
        </label>
        <p className="muted">
          What matters when evaluating a solution? This context does not choose
          a metric or model.
        </p>
        <div>{initial ? <p>ML objective <strong className="badge">{taskLabel(initial.ml_objective)}</strong></p> : <label>ML objective<select name="ml_objective" defaultValue="binary_classification"><option value="binary_classification">Binary Classification</option><option value="regression">Regression</option></select></label>}<p className="muted">The task is immutable and cannot be changed after Project creation.</p></div>
        {error && <Alert>{error}</Alert>}
        <Button variant="primary" type="submit">
          {busy ? "Saving…" : submitLabel}
        </Button>
      </fieldset>
    </form>
  );
}
