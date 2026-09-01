import * as React from "react";
import SideNavigation from "@cloudscape-design/components/side-navigation";

export default function AppSideNavigation({ activeHref, onFollow }) {
  return (
    <SideNavigation
      activeHref={activeHref}
      header={{ href: "#/", text: "MySQL Upgrader" }}
      onFollow={onFollow}
      items={[
        {
          type: "section",
          text: "Database Management",
          items: [
            { type: "link", text: "Upload Configuration", href: "#/upload" },
            { type: "link", text: "Config Generator", href: "#/config-generator" },
            { type: "link", text: "Instance Selection",  href: "#/instances" },
            { type: "link", text: "Upgrade Status",      href: "#/status" },
            { type: "link", text: "Upgrade History",     href: "#/history" }
          ]
        },
        {
          type: "section",
          text: "Configuration",
          items: [
            { type: "link", text: "API Settings", href: "#/api-settings" },
            { type: "link", text: "Default Parameters", href: "#/parameters" },
            { type: "link", text: "Backup Configuration", href: "#/backup" }
          ]
        },
        {
          type: "section",
          text: "Monitoring & Logs",
          items: [
            { type: "link", text: "Upgrade Logs", href: "#/logs" },
            { type: "link", text: "Performance Metrics", href: "#/metrics" },
            { type: "link", text: "Error Reports", href: "#/errors" }
          ]
        },
        {
          type: "section",
          text: "Tools & Utilities",
          items: [
            { type: "link", text: "CSV Template Generator", href: "#/template" },
            { type: "link", text: "Validation Tool", href: "#/validate" },
            { type: "link", text: "Rollback Planner", href: "#/rollback" }
          ]
        },
        {
          type: "section",
          text: "Help & Support",
          items: [
            { type: "link", text: "Getting Started", href: "#/getting-started" },
            { type: "link", text: "Best Practices", href: "#/best-practices" },
            { type: "link", text: "Troubleshooting", href: "#/troubleshooting" },
            { 
              type: "link", 
              text: "AWS RDS Documentation", 
              href: "https://docs.aws.amazon.com/rds/",
              external: true
            }
          ]
        }
      ]}
    />
  );
}
