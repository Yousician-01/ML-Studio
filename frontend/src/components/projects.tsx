"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Project } from "@/lib/api/projects";
import { ProjectForm } from "@/components/project-form";

export function Projects() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api
      .projects(controller.signal)
      .then(setProjects)
      .catch((error) => {
        if (!controller.signal.aborted) setError(error.message);
      });
    return () => controller.abort();
  }, [attempt]);
  return (
    <main>
      <p className="eyebrow">Your local workspace</p>
      <h1>Projects</h1>
      <p className="intro">
        Start with a prediction problem. Bring your CSV, inspect the source, and
        choose a target.
      </p>
      <div className="project-grid">
        <section className="panel" aria-labelledby="projects-title">
          <h2 id="projects-title">Your Projects</h2>
          {error ? (
            <div role="alert">
              <p className="error">{error}</p>
              <button
                onClick={() => {
                  setError("");
                  setAttempt((v) => v + 1);
                }}
              >
                Retry
              </button>
            </div>
          ) : projects === null ? (
            <p role="status">Loading Projects…</p>
          ) : projects.length === 0 ? (
            <p className="muted">
              No Projects yet. Create your first Project to begin.
            </p>
          ) : (
            <ul className="project-list">
              {projects.map((project) => (
                <li key={project.id}>
                  <Link href={`/projects/${project.id}`}>
                    <strong>{project.name}</strong>
                  </Link>
                  <p>{project.problem_statement}</p>
                  <small className="muted">
                    Updated {new Date(project.updated_at).toLocaleDateString()}
                  </small>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="panel" aria-labelledby="create-title">
          <h2 id="create-title">Create a Project</h2>
          <ProjectForm
            submitLabel="Create Project"
            onSave={async (input) => {
              const project = await api.createProject(input);
              router.push(`/projects/${project.id}`);
            }}
          />
        </section>
      </div>
    </main>
  );
}
