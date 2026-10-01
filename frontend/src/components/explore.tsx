"use client";

import { useEffect, useState } from "react";
import { api, type Dataset } from "@/lib/api/projects";
import type {
  ColumnProfile,
  Frequency,
  NumericProfile,
  Profile,
} from "@/lib/api/profiles";
import { displayScalar } from "@/lib/api/scalars";
import { Alert, Button, EmptyState, Loading, Panel, Stats } from "./ui";

const percent = (value: number) => `${value.toFixed(1)}%`;
const number = (value: number | null) =>
  value === null
    ? "Unavailable"
    : new Intl.NumberFormat(undefined, { maximumSignificantDigits: 6 }).format(
        value,
      );

function Frequencies({
  values,
  other = 0,
}: {
  values: Frequency[];
  other?: number;
}) {
  const max = Math.max(1, ...values.map((item) => item.count), other);
  return (
    <div className="table-scroll">
      <table className="distribution-table">
        <thead>
          <tr>
            <th>Value</th>
            <th>Frequency</th>
            <th>Count</th>
            <th>% non-missing</th>
          </tr>
        </thead>
        <tbody>
          {values.map((item, index) => (
            <tr key={index}>
              <th scope="row" className="wrap">
                {displayScalar(item.value, true)}
                {item.label_truncated && <small>… (label shortened)</small>}
              </th>
              <td>
                <div className="bar-track" aria-hidden="true">
                  <div
                    className="bar-fill"
                    style={{ width: `${(item.count / max) * 100}%` }}
                  />
                </div>
              </td>
              <td>{item.count.toLocaleString()}</td>
              <td>{percent(item.percentage)}</td>
            </tr>
          ))}
          {other > 0 && (
            <tr>
              <th>Other values combined</th>
              <td>
                <div className="bar-track" aria-hidden="true">
                  <div
                    className="bar-fill muted-bar"
                    style={{ width: `${(other / max) * 100}%` }}
                  />
                </div>
              </td>
              <td>{other.toLocaleString()}</td>
              <td>
                {percent(
                  (100 * other) /
                    (other + values.reduce((sum, item) => sum + item.count, 0)),
                )}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function Boxplot({ stats }: { stats: NumericProfile }) {
  const { lower_whisker: low, upper_whisker: high, q1, median, q3 } = stats;
  if (
    low === null ||
    high === null ||
    q1 === null ||
    q3 === null ||
    median === null
  )
    return null;
  const x = (value: number) =>
    high === low ? 300 : 40 + ((value - low) / (high - low)) * 520;
  return (
    <figure className="boxplot">
      <figcaption>Boxplot · 1.5 × IQR whiskers</figcaption>
      <svg
        role="img"
        aria-label={`Lower whisker ${number(low)}, Q1 ${number(q1)}, median ${number(median)}, Q3 ${number(q3)}, upper whisker ${number(high)}. ${stats.outlier_count} observations beyond whiskers.`}
        viewBox="0 0 600 100"
      >
        <line x1={x(low)} x2={x(high)} y1="38" y2="38" className="plot-line" />
        <rect
          x={x(q1)}
          y="20"
          width={Math.max(1, x(q3) - x(q1))}
          height="36"
          className="plot-box"
        />
        <line
          x1={x(median)}
          x2={x(median)}
          y1="20"
          y2="56"
          className="plot-line"
        />
        {[low, high].map((v, i) => (
          <line
            key={i}
            x1={x(v)}
            x2={x(v)}
            y1="25"
            y2="51"
            className="plot-line"
          />
        ))}
        <text x="40" y="85" textAnchor="start">
          {number(low)}
        </text>
        <text x="560" y="85" textAnchor="end">
          {number(high)}
        </text>
      </svg>
      <p className="muted">
        {stats.outlier_count.toLocaleString()} observations beyond the whiskers.
        Source rows are unchanged.
      </p>
    </figure>
  );
}

function ColumnDetail({ column }: { column: ColumnProfile }) {
  const stats = column.numeric;
  return (
    <div className="column-detail">
      <div className="section-heading">
        <h3 className="wrap">{column.name}</h3>
        <span className="badge">{column.semantic_type}</span>
      </div>
      <Stats
        values={[
          {
            label: "Non-missing",
            value: column.non_missing_count.toLocaleString(),
          },
          {
            label: "Missing",
            value: percent(column.missing_percentage),
            detail: `${column.missing_count.toLocaleString()} rows`,
          },
          {
            label: "Distinct values",
            value: column.distinct_count.toLocaleString(),
            detail: `${percent(column.uniqueness_percentage)} of non-missing rows`,
          },
        ]}
      />
      {column.identifier && (
        <Alert tone="info">
          This column is currently classified as Identifier. This is a semantic
          interpretation, not a feature-exclusion recommendation.
        </Alert>
      )}
      {column.high_cardinality && (
        <Alert tone="info">
          High cardinality: {column.distinct_count.toLocaleString()} distinct
          values across {column.non_missing_count.toLocaleString()} non-missing
          rows. Rule: at least 20 distinct values and at least 50% uniqueness
          for discrete/text/identifier columns.
        </Alert>
      )}
      {column.unavailable_reason && (
        <p className="muted">{column.unavailable_reason}</p>
      )}
      {column.frequencies && column.frequencies.length > 0 && (
        <>
          <h4>Most frequent values</h4>
          <Frequencies values={column.frequencies} other={column.other_count} />
          <p className="muted">
            Up to 10 values; ties use first source occurrence. Missing values
            are counted separately.
          </p>
        </>
      )}
      {stats && (
        <>
          <div className="table-scroll">
            <table>
              <caption>
                Numerical summary · sample standard deviation; linearly
                interpolated quartiles
              </caption>
              <thead>
                <tr>
                  {[
                    "Minimum",
                    "Q1",
                    "Median",
                    "Q3",
                    "Maximum",
                    "Mean",
                    "Std. deviation",
                  ].map((label) => (
                    <th key={label}>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>{displayScalar(stats.minimum)}</td>
                  <td>{number(stats.q1)}</td>
                  <td>{number(stats.median)}</td>
                  <td>{number(stats.q3)}</td>
                  <td>{displayScalar(stats.maximum)}</td>
                  <td>{number(stats.mean)}</td>
                  <td>{number(stats.standard_deviation)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          {stats.unavailable_reason ? (
            <Alert tone="info">{stats.unavailable_reason}</Alert>
          ) : (
            <>
              <Boxplot stats={stats} />
              <h4>Distribution</h4>
              <div className="table-scroll">
                <table className="distribution-table">
                  <thead>
                    <tr>
                      <th>Bin range</th>
                      <th>Frequency</th>
                      <th>Count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.histogram.map((bin, index) => (
                      <tr key={index}>
                        <th scope="row">
                          {number(bin.lower)} – {number(bin.upper)}
                        </th>
                        <td>
                          <div className="bar-track" aria-hidden="true">
                            <div
                              className="bar-fill"
                              style={{
                                width: `${(bin.count / Math.max(1, ...stats.histogram.map((b) => b.count))) * 100}%`,
                              }}
                            />
                          </div>
                        </td>
                        <td>{bin.count.toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="muted">
                Up to 10 equal-width bins over observed min–max; repeated edges
                collapse at floating-point precision, and constant data uses one bin.
                Lower edge included, upper edge excluded except in the
                final bin. Labels rounded to 6 significant digits.
              </p>
            </>
          )}
        </>
      )}
    </div>
  );
}

export function Explore({
  projectId,
  dataset,
  onReload,
}: {
  projectId: string;
  dataset: Pick<Dataset, "id" | "revision"> | null;
  onReload: () => void;
}) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const id = dataset?.id,
    revision = dataset?.revision;
  useEffect(() => {
    if (!id || revision === undefined) return;
    const controller = new AbortController();
    api
      .profile(projectId, { id, revision }, offset, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) {
          setProfile(value);
          setLoading(false);
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setProfile(null);
          setError(error.message);
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [projectId, id, revision, offset]);
  if (!dataset)
    return (
      <Panel title="Explore">
        <EmptyState title="Add a source Dataset first">
          <p>
            Upload a CSV on Data to inspect its distributions and source
            observations.
          </p>
        </EmptyState>
      </Panel>
    );
  if (error)
    return (
      <Panel title="Explore could not load">
        <Alert>{error}</Alert>
        <Button onClick={onReload}>Reload current Dataset</Button>
      </Panel>
    );
  if (loading || !profile)
    return (
      <Panel title="Explore">
        <Loading>Profiling the source Dataset…</Loading>
      </Panel>
    );
  const column = profile.columns[selected];
  const correlation = profile.correlation;
  return (
    <div className="explore-view">
      <div className="section-heading">
        <div>
          <h2>Explore</h2>
          <p className="muted">
            Full source observations · {profile.original_filename}
          </p>
        </div>
        <span className="badge subtle">
          Snapshot revision {profile.revision}
        </span>
      </div>
      <Alert tone="info">
        Full-source descriptive analysis. No rows are transformed or removed,
        and no preprocessing is fitted.
      </Alert>
      <Panel title="Dataset overview">
        <Stats
          values={[
            { label: "Rows", value: profile.row_count.toLocaleString() },
            { label: "Columns", value: profile.column_count },
            { label: "Feature candidates", value: profile.feature_count },
            {
              label: "Missing cells",
              value: percent(profile.missing_percentage),
              detail: profile.missing_cells.toLocaleString(),
            },
            {
              label: "Duplicate rows",
              value: profile.duplicate_rows.toLocaleString(),
              detail: percent(profile.duplicate_percentage),
            },
          ]}
        />
        <p className="muted">
          Duplicate count excludes the first occurrence of each identical row.
        </p>
        <div className="semantic-composition">
          {Object.entries(profile.semantic_counts).map(([type, count]) => (
            <span className="badge" key={type}>
              {type} <strong>{count}</strong>
            </span>
          ))}
        </div>
      </Panel>
      <Panel
        title="Target distribution"
        description={profile.target ? profile.target.column : undefined}
      >
        {profile.target ? (
          <>
            <Frequencies values={profile.target.classes} />
            <p className="muted">
              Percentages use{" "}
              {profile.target.non_missing_count.toLocaleString()} non-missing
              target rows. {profile.target.missing_count.toLocaleString()}{" "}
              missing target rows are shown separately and are eligible for
              exclusion during later execution.
            </p>
            <p>
              Largest class:{" "}
              <strong>{percent(profile.target.majority_percentage)}</strong> of
              non-missing targets. These proportions describe class balance; no
              quality judgement or resampling recommendation is made.
            </p>
          </>
        ) : (
          <EmptyState title="No target selected">
            <p>
              Select a binary target on Data to see class proportions. Other
              source analysis is available below.
            </p>
          </EmptyState>
        )}
      </Panel>
      <Panel
        title="Column observations"
        description={`Columns ${profile.column_offset + 1}–${Math.min(profile.column_offset + profile.column_limit, profile.column_count)} of ${profile.column_count}. Select a row for its distribution.`}
        action={
          <div className="actions">
            <Button
              disabled={offset === 0}
              onClick={() => {
                setOffset(Math.max(0, offset - profile.column_limit));
                setSelected(0);
                setLoading(true);
              }}
            >
              Previous
            </Button>
            <Button
              disabled={offset + profile.column_limit >= profile.column_count}
              onClick={() => {
                setOffset(offset + profile.column_limit);
                setSelected(0);
                setLoading(true);
              }}
            >
              Next
            </Button>
          </div>
        }
      >
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {[
                  "Column",
                  "Semantic type",
                  "Missing",
                  "Missing %",
                  "Distinct",
                  "Observations",
                ].map((label) => (
                  <th key={label}>{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {profile.columns.map((item, index) => (
                <tr
                  key={item.name}
                  className={selected === index ? "selected-row" : ""}
                >
                  <th scope="row">
                    <button
                      className="column-link"
                      aria-pressed={selected === index}
                      onClick={() => setSelected(index)}
                    >
                      {item.name}
                    </button>
                  </th>
                  <td>{item.semantic_type}</td>
                  <td>{item.missing_count.toLocaleString()}</td>
                  <td>{percent(item.missing_percentage)}</td>
                  <td>{item.distinct_count.toLocaleString()}</td>
                  <td>
                    {item.identifier && (
                      <span className="badge">Identifier</span>
                    )}
                    {item.high_cardinality && (
                      <span className="badge">High cardinality</span>
                    )}
                    {!item.identifier && !item.high_cardinality && "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {column ? (
          <ColumnDetail column={column} />
        ) : (
          <EmptyState title="No columns on this page">
            Return to a previous page.
          </EmptyState>
        )}
      </Panel>
      <Panel
        title="Feature correlation"
        description="Pearson correlation of continuous numeric feature candidates. Targets, excluded columns, and categorical/identifier columns are omitted."
      >
        <p className="muted">
          First {correlation.columns.length} of {correlation.eligible_count}{" "}
          eligible columns in source order (limit {correlation.column_limit}).
          Pairwise complete observations; at least two varying observations
          required. — means constant, insufficient, or precision-limited data.
        </p>
        {correlation.unavailable_reason ? (
          <EmptyState title="Correlation unavailable">
            {correlation.unavailable_reason}
          </EmptyState>
        ) : (
          <div className="table-scroll">
            <table className="correlation-table">
              <caption>
                Each cell shows correlation and its pairwise non-missing row
                count.
              </caption>
              <thead>
                <tr>
                  <th>Feature</th>
                  {correlation.columns.map((name) => (
                    <th key={name}>{name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {correlation.columns.map((name, i) => (
                  <tr key={name}>
                    <th scope="row">{name}</th>
                    {correlation.values[i].map((value, j) => (
                      <td
                        key={j}
                        className={value === null ? "" : "correlation-cell"}
                        style={
                          value === null
                            ? undefined
                            : {
                                backgroundColor: `rgba(101, 69, 47, ${Math.abs(value) * 0.18})`,
                              }
                        }
                      >
                        <strong>
                          {value === null ? "—" : value.toFixed(3)}
                        </strong>
                        <small>n={correlation.pair_counts[i][j]}</small>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
