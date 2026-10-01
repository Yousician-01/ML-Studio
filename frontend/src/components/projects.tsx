"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Project } from "@/lib/api/projects";
import { ProjectForm } from "./project-form";
import { DeleteProject } from "./delete-project";
import { Alert, Button, Dialog, EmptyState, Loading } from "./ui";

export function Projects() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<Project | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    api
      .projects(controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setProjects(value);
      })
      .catch((error) => {
        if (!controller.signal.aborted) setError(error.message);
      });
    return () => controller.abort();
  }, [attempt]);
  return (
    <main>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Workspace</p>
          <h1>Projects</h1>
          <p className="muted">
            Your prediction problems, source data, and working context.
          </p>
        </div>
        <Button variant="primary" onClick={() => setCreating(true)}>
          New Project
        </Button>
      </div>
      {error && (
        <Alert>
          {error}
          <Button
            onClick={() => {
              setError("");
              setAttempt((v) => v + 1);
            }}
          >
            Retry
          </Button>
        </Alert>
      )}
      {projects === null ? (
        !error && <Loading>Loading Projects…</Loading>
      ) : projects.length === 0 ? (
        <section className="panel">
          <EmptyState title="Start with a prediction problem">
            <p>Create a Project, bring a CSV, and explore the source.</p>
            <Button variant="primary" onClick={() => setCreating(true)}>
              Create your first Project
            </Button>
          </EmptyState>
        </section>
      ) : (
        <section className="panel project-surface" aria-label="Projects">
          <div className="list-heading">
            <span>Project / prediction problem</span>
            <span>Last updated</span>
          </div>
          <ul className="project-list">
            {projects.map((project) => (
              <li key={project.id}>
                <div className="project-context">
                  <Link
                    className="project-name"
                    href={`/projects/${project.id}`}
                  >
                    {project.name}
                  </Link>
                  <p>{project.problem_statement}</p>
                  {project.description && (
                    <small className="muted">{project.description}</small>
                  )}
                  <div>
                    <span className="badge">Binary classification</span>
                    <span className="badge subtle">
                      {project.active_dataset_id
                        ? "Dataset attached"
                        : "No Dataset"}
                    </span>
                  </div>
                </div>
                <div className="project-actions">
                  <time dateTime={project.updated_at}>
                    {new Date(project.updated_at).toLocaleDateString()}
                  </time>
                  <div className="actions">
                    <Link
                      className="button button-secondary"
                      href={`/projects/${project.id}`}
                    >
                      Open
                    </Link>
                    <Button
                      variant="danger"
                      aria-label={`Delete ${project.name}`}
                      onClick={() => setDeleting(project)}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
      {creating && (
        <Dialog title="Create Project" onClose={() => setCreating(false)}>
          <ProjectForm
            submitLabel="Create Project"
            onSave={async (input) => {
              const project = await api.createProject(input);
              router.push(`/projects/${project.id}`);
            }}
          />
        </Dialog>
      )}
      {deleting && (
        <DeleteProject
          project={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={() => {
            setProjects(
              (items) =>
                items?.filter((item) => item.id !== deleting.id) ?? null,
            );
            setDeleting(null);
          }}
        />
      )}
    </main>
  );
}
