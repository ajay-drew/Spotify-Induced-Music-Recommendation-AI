describe("SIMRAI web UI – mood to queue journey", () => {
  it("brews a queue from a mood description", () => {
    // Stub the FastAPI /queue endpoint so the test is backend-independent.
    cy.intercept("POST", "**/queue", {
      statusCode: 200,
      body: {
        mood: "rainy midnight drive",
        mood_vector: { valence: 0.4, energy: 0.3 },
        summary: "Test queue summary",
        tracks: [
          {
            name: "Test Track One",
            artists: "Test Artist",
            uri: "spotify:track:test1",
            valence: 0.4,
            energy: 0.3,
          },
        ],
      },
    }).as("brewQueue");

    cy.visit("/");

    cy.get("textarea")
      .should("be.visible")
      .type("rainy midnight drive with someone you miss");

    cy.contains("button", "Generate Queue").click();

    cy.wait("@brewQueue");

    cy.contains("Queue").should("be.visible");
    cy.get("table tbody tr").should("have.length.at.least", 1);
    cy.contains("Test Track One").should("be.visible");
  });

  it("validates postMessage origin for OAuth callback", () => {
    cy.visit("/");

    // Spy on console.warn to check origin validation
    cy.window().then((win) => {
      cy.spy(win.console, "warn").as("consoleWarn");
    });

    // Simulate postMessage from untrusted origin
    cy.window().then((win) => {
      const maliciousEvent = new MessageEvent("message", {
        data: { type: "simrai-spotify-connected" },
        origin: "https://evil-site.com",  // Wrong origin
      });
      win.dispatchEvent(maliciousEvent);
    });

    // Should log warning and not connect
    cy.get("@consoleWarn").should(
      "be.calledWithMatch",
      /Rejected postMessage from untrusted origin/
    );
  });

  it("accepts postMessage from trusted origin", () => {
    // Stub the /api/me endpoint
    cy.intercept("GET", "**/api/me", {
      statusCode: 200,
      body: {
        id: "test_user",
        display_name: "Test User",
        avatar_url: null,
      },
    }).as("getMe");

    cy.visit("/");

    // Simulate postMessage from trusted origin
    cy.window().then((win) => {
      const trustedEvent = new MessageEvent("message", {
        data: { type: "simrai-spotify-connected" },
        origin: "http://localhost:8000",  // Correct origin
      });
      win.dispatchEvent(trustedEvent);
    });

    // Should accept and fetch user profile
    cy.wait("@getMe");
    cy.contains("Spotify connected").should("be.visible");
  });

  it("renders the queue correctly on a laptop-sized viewport", () => {
    cy.viewport("macbook-15");

    cy.intercept("POST", "**/queue", {
      statusCode: 200,
      body: {
        mood: "focus deep work",
        mood_vector: { valence: 0.6, energy: 0.5 },
        summary: "Desktop responsive test",
        tracks: [
          {
            name: "Laptop Track",
            artists: "Responsive Artist",
            uri: "spotify:track:laptop1",
            valence: 0.6,
            energy: 0.5,
          },
        ],
      },
    }).as("desktopQueue");

    cy.visit("/");

    cy.get("textarea").type("focus deep work");
    cy.contains("button", "Brew Queue").click();

    cy.wait("@desktopQueue");

    // Queue table should be visible with at least one row
    cy.contains("Queue").should("be.visible");
    cy.get("table tbody tr").should("have.length.at.least", 1);
    cy.contains("Laptop Track").should("be.visible");

    // On larger screens the URI column header should be visible
    cy.contains("th", "URI").should("be.visible");
  });

  it("renders the queue correctly on a mobile-sized viewport", () => {
    cy.viewport("iphone-6");

    cy.intercept("POST", "**/queue", {
      statusCode: 200,
      body: {
        mood: "late night walk",
        mood_vector: { valence: 0.5, energy: 0.4 },
        summary: "Mobile responsive test",
        tracks: [
          {
            name: "Mobile Track",
            artists: "Responsive Artist",
            uri: "spotify:track:mobile1",
            valence: 0.5,
            energy: 0.4,
          },
        ],
      },
    }).as("mobileQueue");

    cy.visit("/");

    cy.get("textarea").type("late night walk under city lights");
    cy.contains("button", "Brew Queue").click();

    cy.wait("@mobileQueue");

    // Queue table should still render correctly on small screens
    cy.contains("Queue").should("be.visible");
    cy.get("table tbody tr").should("have.length.at.least", 1);
    cy.contains("Mobile Track").should("be.visible");

    // The URI column uses `hidden sm:table-cell`, so it should not be visible on mobile
    cy.contains("th", "URI").should("not.be.visible");
  });
});


