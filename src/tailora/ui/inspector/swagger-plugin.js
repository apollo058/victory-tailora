/** Swagger UI에 Tailora Inspector 탭을 추가하는 공식 plugin adapter입니다. */
(function registerTailoraSwaggerPlugin(windowObject) {
  "use strict";

  /** Inspector의 같은 origin URL 설정을 안전하게 읽습니다. */
  function getInspectorUrl() {
    const config = windowObject.TAILORA_SWAGGER_CONFIG || {};
    return typeof config.inspectorUrl === "string" ? config.inspectorUrl : "";
  }

  /** 탭 전환에 사용하는 접근 가능한 버튼을 생성합니다. */
  function createTabButton(
    React,
    label,
    isActive,
    onSelect,
    onSiblingSelect,
    controlledPanelId,
    siblingTabId,
    tabId,
  ) {
    return React.createElement(
      "button",
      {
        type: "button",
        id: tabId,
        className: "tailora-swagger-tab",
        role: "tab",
        "aria-selected": isActive,
        "aria-controls": controlledPanelId,
        tabIndex: isActive ? 0 : -1,
        onClick: onSelect,
        onKeyDown: function handleTabKeyboard(event) {
          if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            event.preventDefault();
            onSiblingSelect();
            const siblingTab = document.getElementById(siblingTabId);
            if (siblingTab) {
              siblingTab.focus();
            }
          }
        },
      },
      label,
    );
  }

  /** 처음 Inspector를 선택한 뒤에만 iframe을 포함한 패널을 생성합니다. */
  function createInspectorPanel(React, isActive, isLoaded) {
    return React.createElement(
      "section",
      {
        id: "tailora-inspector-panel",
        className: "tailora-swagger-panel",
        role: "tabpanel",
        "aria-labelledby": "tailora-inspector-tab",
        hidden: !isActive,
      },
      isLoaded
        ? React.createElement("iframe", {
            className: "tailora-swagger-frame",
            title: "Tailora Inspector",
            src: getInspectorUrl(),
          })
        : null,
    );
  }

  /** API Docs 탭의 Swagger UI를 감싸는 패널을 생성합니다. */
  function createDocsPanel(React, BaseLayout, props, isActive) {
    return React.createElement(
      "section",
      {
        id: "tailora-docs-panel",
        className: "tailora-swagger-panel",
        role: "tabpanel",
        "aria-labelledby": "tailora-docs-tab",
        hidden: !isActive,
      },
      React.createElement(BaseLayout, props),
    );
  }

  /** API Docs와 Inspector 탭 navigation을 생성합니다. */
  function createTabList(React, docsActive, selectDocs, selectInspector) {
    return React.createElement(
      "nav",
      {
        className: "tailora-swagger-tabs",
        role: "tablist",
        "aria-label": "API 문서와 Inspector 전환",
      },
      createTabButton(
        React,
        "API Docs",
        docsActive,
        selectDocs,
        selectInspector,
        "tailora-docs-panel",
        "tailora-inspector-tab",
        "tailora-docs-tab",
      ),
      createTabButton(
        React,
        "Inspector",
        !docsActive,
        selectInspector,
        selectDocs,
        "tailora-inspector-panel",
        "tailora-docs-tab",
        "tailora-inspector-tab",
      ),
    );
  }

  /** Swagger UI layout component를 생성해 탭 전환 상태를 독립적으로 유지합니다. */
  function createTailoraDocsLayout(React, BaseLayout) {
    /** 탭을 전환해도 기존 Swagger UI와 Inspector 화면을 모두 유지합니다. */
    return function TailoraDocsLayout(props) {
      const tabState = React.useState("docs");
      const activeTab = tabState[0];
      const setActiveTab = tabState[1];
      const inspectorState = React.useState(false);
      const inspectorLoaded = inspectorState[0];
      const setInspectorLoaded = inspectorState[1];
      const docsActive = activeTab === "docs";

      /** API Docs 탭으로 돌아가 기존 문서 상태를 보존합니다. */
      function selectDocs() {
        setActiveTab("docs");
      }

      /** Inspector를 처음 선택할 때 화면을 로드하고 탭을 전환합니다. */
      function selectInspector() {
        setInspectorLoaded(true);
        setActiveTab("inspector");
      }

      return React.createElement(
        "div",
        { className: "tailora-swagger-layout" },
        createTabList(React, docsActive, selectDocs, selectInspector),
        createDocsPanel(React, BaseLayout, props, docsActive),
        createInspectorPanel(React, !docsActive, inspectorLoaded),
      );
    };
  }

  /** Swagger UI BaseLayout을 보존하며 API Docs와 Inspector 탭을 제공하는 plugin입니다. */
  function TailoraSwaggerPlugin(system) {
    const React = system.React;
    const BaseLayout = system.getComponent("BaseLayout", true);
    return {
      components: {
        TailoraDocsLayout: createTailoraDocsLayout(React, BaseLayout),
      },
    };
  }

  windowObject.TailoraSwaggerPlugin = TailoraSwaggerPlugin;
})(window);
