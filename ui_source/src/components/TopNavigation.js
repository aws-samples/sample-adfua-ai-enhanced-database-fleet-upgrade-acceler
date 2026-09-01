import * as React from "react";
import TopNavigation from "@cloudscape-design/components/top-navigation";

export default function AppTopNavigation() {
  return (
    <TopNavigation
      identity={{
        href: "#",
        title: "MySQL Database Upgrader",
        logo: {
          src: "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIiIGhlaWdodD0iMzIiIHZpZXdCb3g9IjAgMCAzMiAzMiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHJlY3Qgd2lkdGg9IjMyIiBoZWlnaHQ9IjMyIiByeD0iNCIgZmlsbD0iIzIzMkYzRSIvPgo8cGF0aCBkPSJNOCAxMkgxNlYyMEg4VjEyWiIgZmlsbD0iI0ZGOTkwMCIvPgo8cGF0aCBkPSJNMTYgOEgyNFYxNkgxNlY4WiIgZmlsbD0iIzAwN0RGRiIvPgo8L3N2Zz4K",
          alt: "MySQL Upgrader"
        }
      }}
      utilities={[
        {
          type: "button",
          text: "Documentation",
          href: "https://docs.aws.amazon.com/rds/",
          external: true,
          externalIconAriaLabel: " (opens in a new tab)"
        },
        {
          type: "button",
          iconName: "notification",
          title: "Notifications",
          ariaLabel: "Notifications (unread)",
          badge: false,
          disableUtilityCollapse: false
        },
        {
          type: "menu-dropdown",
          iconName: "settings",
          ariaLabel: "Settings",
          title: "Settings",
          items: [
            {
              id: "settings-api",
              text: "API Configuration"
            },
            {
              id: "settings-preferences",
              text: "User Preferences"
            },
            {
              id: "settings-export",
              text: "Export Settings"
            }
          ]
        },
        {
          type: "menu-dropdown",
          text: "Database Admin",
          description: "admin@company.com",
          iconName: "user-profile",
          items: [
            { id: "profile", text: "Profile" },
            { id: "preferences", text: "Preferences" },
            { id: "security", text: "Security" },
            {
              id: "support-group",
              text: "Support",
              items: [
                {
                  id: "documentation",
                  text: "AWS RDS Documentation",
                  href: "https://docs.aws.amazon.com/rds/",
                  external: true,
                  externalIconAriaLabel: " (opens in new tab)"
                },
                {
                  id: "mysql-docs",
                  text: "MySQL Documentation",
                  href: "https://dev.mysql.com/doc/",
                  external: true,
                  externalIconAriaLabel: " (opens in new tab)"
                },
                { id: "support", text: "Contact Support" },
                {
                  id: "feedback",
                  text: "Send Feedback",
                  href: "#",
                  external: true,
                  externalIconAriaLabel: " (opens in new tab)"
                }
              ]
            },
            { id: "signout", text: "Sign out" }
          ]
        }
      ]}
    />
  );
}
