import React from "react";

import { Card, Chip, SectionHeader } from "./uiPrimitives";
import { theme } from "../theme";
import { buildThreatStory } from "../utils/investigationWorkflow";

function ThreatStoryView({ context }) {
  const story = buildThreatStory(context);
  return (
    <Card aria-label="Threat Story">
      <SectionHeader
        eyebrow="Threat Story"
        title="Investigation narrative"
        subtitle="Read-only story from loaded alert, incident, timeline, response, and private observation data."
      />
      <div style={bodyStyle}>
        <section style={progressionStyle} aria-label="Attack progression">
          <div style={sectionHeaderStyle}>
            <strong>Attack progression</strong>
            <Chip tone={story.progressionStatus === "available" ? "info" : "neutral"}>
              {story.progressionStatus}
            </Chip>
          </div>
          {story.progression.length ? (
            <ol style={progressionListStyle}>
              {story.progression.map((step) => (
                <li key={step.id} style={progressionItemStyle}>
                  <strong>{step.label}</strong>
                  <span style={mutedStyle}>{step.timestamp || "time unavailable"} • {step.source}</span>
                  <p style={paragraphStyle}>{step.detail}</p>
                </li>
              ))}
            </ol>
          ) : (
            <p style={mutedParagraphStyle}>No ordered progression is supported by the loaded evidence.</p>
          )}
        </section>
        <div style={gridStyle}>
          {story.sections.map((section) => (
            <section key={section.id} style={storyCardStyle} aria-label={section.title}>
              <div style={sectionHeaderStyle}>
                <strong>{section.title}</strong>
                <Chip tone={section.status === "available" ? "info" : "neutral"}>{section.status}</Chip>
              </div>
              <p style={paragraphStyle}>{section.body}</p>
              <span style={mutedStyle}>Source: {section.source}</span>
            </section>
          ))}
        </div>
      </div>
    </Card>
  );
}

const bodyStyle = { padding: theme.spacing.lg, display: "grid", gap: theme.spacing.lg };
const gridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: theme.spacing.md };
const progressionStyle = { border: `1px solid ${theme.color.border}`, borderRadius: theme.radius.sm, padding: theme.spacing.md, backgroundColor: theme.color.bg };
const storyCardStyle = { border: `1px solid ${theme.color.border}`, borderRadius: theme.radius.sm, padding: theme.spacing.md, backgroundColor: theme.color.bg };
const sectionHeaderStyle = { display: "flex", justifyContent: "space-between", gap: theme.spacing.sm, alignItems: "center", color: theme.color.text };
const progressionListStyle = { margin: `${theme.spacing.md}px 0 0`, paddingLeft: "22px", display: "grid", gap: theme.spacing.md };
const progressionItemStyle = { color: theme.color.text };
const paragraphStyle = { margin: "8px 0", color: theme.color.textSoft, lineHeight: 1.45 };
const mutedParagraphStyle = { margin: `${theme.spacing.md}px 0 0`, color: theme.color.textMuted };
const mutedStyle = { display: "block", color: theme.color.textMuted, fontSize: "12px" };

export default ThreatStoryView;
