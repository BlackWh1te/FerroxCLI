"""Smart project context analyzer for Ferrox agent.

Provides enhanced project understanding with dependency graphs,
monorepo detection, configuration file detection, and build system integration.
"""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Import tracer
from opentelemetry import trace

tracer = trace.get_tracer(__name__)


@dataclass
class ProjectConfig:
    """Detected project configuration."""
    config_type: str  # "package.json", "pyproject.toml", "Cargo.toml", etc.
    path: str
    data: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    dev_dependencies: List[str] = field(default_factory=list)
    scripts: Dict[str, str] = field(default_factory=dict)


@dataclass
class BuildSystem:
    """Detected build system."""
    name: str  # "npm", "yarn", "pnpm", "cargo", "pip", "make", "gradle", "maven"
    config_path: str
    build_command: str = ""
    test_command: str = ""
    install_command: str = ""


@dataclass
class ProjectContext:
    """Complete project context analysis."""
    project_root: str
    project_type: str  # "monorepo", "single", "workspace"
    language: str  # "python", "javascript", "rust", "go", "java", etc.
    configs: List[ProjectConfig] = field(default_factory=list)
    build_systems: List[BuildSystem] = field(default_factory=list)
    dependency_graph: Dict[str, Set[str]] = field(default_factory=dict)
    workspace_structure: Dict[str, Any] = field(default_factory=dict)
    important_files: List[str] = field(default_factory=list)


class ProjectContextAnalyzer:
    """Analyzes project structure and context."""

    def __init__(self, project_root: str = "."):
        """Initialize the analyzer.
        
        Args:
            project_root: Root directory of the project
        """
        self.project_root = Path(project_root).resolve()
        self.context: Optional[ProjectContext] = None

    def analyze(self) -> ProjectContext:
        """Analyze the project and return context.
        
        Returns:
            Complete project context
        """
        with tracer.start_as_current_span("project_context_analyze") as span:
            span.set_attribute("project_root", str(self.project_root))

            # Detect project type and language
            project_type = self._detect_project_type()
            language = self._detect_language()

            # Detect configurations
            configs = self._detect_configurations()

            # Detect build systems
            build_systems = self._detect_build_systems(configs)

            # Build dependency graph
            dependency_graph = self._build_dependency_graph(configs)

            # Analyze workspace structure
            workspace_structure = self._analyze_workspace_structure()

            # Identify important files
            important_files = self._identify_important_files()

            self.context = ProjectContext(
                project_root=str(self.project_root),
                project_type=project_type,
                language=language,
                configs=configs,
                build_systems=build_systems,
                dependency_graph=dependency_graph,
                workspace_structure=workspace_structure,
                important_files=important_files
            )

            return self.context

    def _detect_project_type(self) -> str:
        """Detect if project is monorepo, single, or workspace."""
        # Check for monorepo indicators
        monorepo_indicators = [
            "lerna.json",
            "nx.json",
            "turbo.json",
            "pnpm-workspace.yaml",
            "packages/",
            "apps/",
            "libs/"
        ]

        for indicator in monorepo_indicators:
            if (self.project_root / indicator).exists():
                return "monorepo"

        # Check for workspace indicators
        workspace_indicators = [
            "go.work",
            "Cargo.toml"  # Rust workspaces
        ]

        for indicator in workspace_indicators:
            if (self.project_root / indicator).exists():
                return "workspace"

        return "single"

    def _detect_language(self) -> str:
        """Detect primary project language."""
        language_indicators = {
            "python": ["pyproject.toml", "requirements.txt", "setup.py", ".python-version"],
            "javascript": ["package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml"],
            "typescript": ["tsconfig.json", "package.json"],
            "rust": ["Cargo.toml", "Cargo.lock"],
            "go": ["go.mod", "go.sum"],
            "java": ["pom.xml", "build.gradle", "gradlew"],
            "ruby": ["Gemfile", "Gemfile.lock"],
            "php": ["composer.json", "composer.lock"],
            "csharp": ["*.csproj", "*.sln"]
        }

        language_scores = defaultdict(int)

        for language, indicators in language_indicators.items():
            for indicator in indicators:
                if "*" in indicator:
                    # Glob pattern
                    for path in self.project_root.glob(indicator):
                        language_scores[language] += 1
                else:
                    if (self.project_root / indicator).exists():
                        language_scores[language] += 1

        if not language_scores:
            return "unknown"

        return max(language_scores.items(), key=lambda x: x[1])[0]

    def _detect_configurations(self) -> List[ProjectConfig]:
        """Detect all project configuration files."""
        configs = []

        # Common config files
        config_patterns = {
            "package.json": "json",
            "package-lock.json": "json",
            "yarn.lock": "yaml",
            "pnpm-lock.yaml": "yaml",
            "tsconfig.json": "json",
            "pyproject.toml": "toml",
            "setup.py": "python",
            "requirements.txt": "text",
            "Cargo.toml": "toml",
            "go.mod": "go",
            "pom.xml": "xml",
            "build.gradle": "gradle",
            "Gemfile": "ruby",
            "composer.json": "json"
        }

        for config_file, config_type in config_patterns.items():
            config_path = self.project_root / config_file
            if config_path.exists():
                config = self._parse_config(config_path, config_type)
                if config:
                    configs.append(config)

        # Check subdirectories for configs (monorepo support)
        if self.context and self.context.project_type == "monorepo":
            for subdir in ["packages", "apps", "libs"]:
                subdir_path = self.project_root / subdir
                if subdir_path.exists():
                    for subconfig_path in subdir_path.rglob("package.json"):
                        config = self._parse_config(subconfig_path, "json")
                        if config:
                            configs.append(config)

        return configs

    def _parse_config(self, config_path: Path, config_type: str) -> Optional[ProjectConfig]:
        """Parse a configuration file."""
        try:
            with open(config_path) as f:
                if config_type == "json":
                    data = json.load(f)
                elif config_type == "toml":
                    # Use tomllib for Python 3.11+, otherwise try toml package
                    try:
                        import tomllib
                        data = tomllib.load(f)
                    except ImportError:
                        try:
                            import toml
                            data = toml.load(f)
                        except ImportError:
                            # Fallback: read as text
                            data = {"raw_content": f.read()}
                elif config_type in ["yaml", "text", "python", "go", "xml", "gradle", "ruby"]:
                    # For now, just read as text
                    data = {"raw_content": f.read()}
                else:
                    return None

            # Extract dependencies
            dependencies = []
            dev_dependencies = []
            scripts = {}

            if config_type == "json":
                dependencies = list(data.get("dependencies", {}).keys())
                dev_dependencies = list(data.get("devDependencies", {}).keys())
                scripts = data.get("scripts", {})
            elif config_type == "toml":
                if "dependencies" in data:
                    dependencies = list(data["dependencies"].keys())
                if "dev-dependencies" in data:
                    dev_dependencies = list(data["dev-dependencies"].keys())

            return ProjectConfig(
                config_type=config_path.name,
                path=str(config_path),
                data=data,
                dependencies=dependencies,
                dev_dependencies=dev_dependencies,
                scripts=scripts
            )
        except Exception:
            return None

    def _detect_build_systems(self, configs: List[ProjectConfig]) -> List[BuildSystem]:
        """Detect build systems from configurations."""
        build_systems = []

        for config in configs:
            if config.config_type == "package.json":
                # Detect npm, yarn, pnpm
                lock_files = {
                    "package-lock.json": "npm",
                    "yarn.lock": "yarn",
                    "pnpm-lock.yaml": "pnpm"
                }

                for lock_file, system_name in lock_files.items():
                    lock_path = self.project_root / lock_file
                    if lock_path.exists():
                        build_systems.append(BuildSystem(
                            name=system_name,
                            config_path=str(lock_path),
                            build_command=config.scripts.get("build", ""),
                            test_command=config.scripts.get("test", ""),
                            install_command=f"{system_name} install"
                        ))
                        break

            elif config.config_type == "Cargo.toml":
                build_systems.append(BuildSystem(
                    name="cargo",
                    config_path=config.path,
                    build_command="cargo build",
                    test_command="cargo test",
                    install_command="cargo build"
                ))

            elif config.config_type == "pyproject.toml":
                build_systems.append(BuildSystem(
                    name="pip",
                    config_path=config.path,
                    build_command="python -m build",
                    test_command="pytest",
                    install_command="pip install -e ."
                ))

            elif config.config_type == "go.mod":
                build_systems.append(BuildSystem(
                    name="go",
                    config_path=config.path,
                    build_command="go build",
                    test_command="go test",
                    install_command="go mod download"
                ))

        # Check for Makefile
        if (self.project_root / "Makefile").exists():
            build_systems.append(BuildSystem(
                name="make",
                config_path=str(self.project_root / "Makefile"),
                build_command="make build",
                test_command="make test",
                install_command="make install"
            ))

        return build_systems

    def _build_dependency_graph(self, configs: List[ProjectConfig]) -> Dict[str, Set[str]]:
        """Build a dependency graph from configurations."""
        graph = defaultdict(set)

        for config in configs:
            config_name = Path(config.path).stem
            for dep in config.dependencies + config.dev_dependencies:
                graph[config_name].add(dep)

        return dict(graph)

    def _analyze_workspace_structure(self) -> Dict[str, Any]:
        """Analyze workspace/monorepo structure."""
        structure = {
            "type": "flat",
            "packages": [],
            "apps": [],
            "libs": [],
            "services": []
        }

        # Check for common monorepo structures
        for subdir in ["packages", "apps", "libs", "services"]:
            subdir_path = self.project_root / subdir
            if subdir_path.exists():
                structure[subdir] = []
                for item in subdir_path.iterdir():
                    if item.is_dir() and not item.name.startswith("."):
                        structure[subdir].append(item.name)
                        structure["type"] = "monorepo"

        return structure

    def _identify_important_files(self) -> List[str]:
        """Identify important project files."""
        important_patterns = [
            "README*",
            "LICENSE*",
            "CHANGELOG*",
            "CONTRIBUTING*",
            ".gitignore",
            ".env*",
            "Dockerfile*",
            "docker-compose*",
            "*.md",
            ".github/**/*",
            ".gitlab-ci.yml",
            "Jenkinsfile",
            "Makefile",
            "*.config.js",
            "*.config.ts"
        ]

        important_files = []

        for pattern in important_patterns:
            if "*" in pattern or "**" in pattern:
                for path in self.project_root.glob(pattern):
                    important_files.append(str(path.relative_to(self.project_root)))
            else:
                if (self.project_root / pattern).exists():
                    important_files.append(pattern)

        return important_files

    def get_context_summary(self) -> str:
        """Get a human-readable summary of project context."""
        if not self.context:
            return "No context analyzed yet. Run analyze() first."

        summary = f"Project Context for {self.context.project_root}\n"
        summary += f"{'=' * 60}\n\n"

        summary += f"Type: {self.context.project_type}\n"
        summary += f"Language: {self.context.language}\n\n"

        if self.context.build_systems:
            summary += "Build Systems:\n"
            for bs in self.context.build_systems:
                summary += f"  - {bs.name} ({bs.config_path})\n"
                if bs.build_command:
                    summary += f"    Build: {bs.build_command}\n"
                if bs.test_command:
                    summary += f"    Test: {bs.test_command}\n"
            summary += "\n"

        if self.context.configs:
            summary += f"Configurations ({len(self.context.configs)}):\n"
            for config in self.context.configs[:5]:  # Show first 5
                summary += f"  - {config.config_type} ({config.path})\n"
            if len(self.context.configs) > 5:
                summary += f"  ... and {len(self.context.configs) - 5} more\n"
            summary += "\n"

        if self.context.workspace_structure.get("type") == "monorepo":
            summary += "Workspace Structure:\n"
            for key, value in self.context.workspace_structure.items():
                if isinstance(value, list) and value:
                    summary += f"  {key}/: {', '.join(value)}\n"
            summary += "\n"

        if self.context.important_files:
            summary += f"Important Files ({len(self.context.important_files)}):\n"
            for file in self.context.important_files[:10]:
                summary += f"  - {file}\n"
            if len(self.context.important_files) > 10:
                summary += f"  ... and {len(self.context.important_files) - 10} more\n"

        return summary

    def find_dependency_cycles(self) -> List[List[str]]:
        """Find circular dependencies in the dependency graph."""
        if not self.context:
            return []

        graph = self.context.dependency_graph
        cycles = []
        visited = set()
        rec_stack = set()

        def dfs(node: str, path: List[str]) -> None:
            if node in rec_stack:
                # Found a cycle
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:] + [node])
                return

            if node in visited:
                return

            visited.add(node)
            rec_stack.add(node)

            for neighbor in graph.get(node, set()):
                dfs(neighbor, path + [node])

            rec_stack.remove(node)

        for node in graph:
            if node not in visited:
                dfs(node, [node])

        return cycles

    def get_build_command(self, system_name: Optional[str] = None) -> str:
        """Get the appropriate build command.
        
        Args:
            system_name: Specific build system to use (auto-detect if None)
        
        Returns:
            Build command string
        """
        if not self.context:
            return ""

        if system_name:
            for bs in self.context.build_systems:
                if bs.name == system_name:
                    return bs.build_command
        else:
            # Auto-detect preferred build system
            priority = ["npm", "yarn", "pnpm", "cargo", "pip", "go", "make"]
            for preferred in priority:
                for bs in self.context.build_systems:
                    if bs.name == preferred:
                        return bs.build_command

        return ""

    def get_test_command(self, system_name: Optional[str] = None) -> str:
        """Get the appropriate test command.
        
        Args:
            system_name: Specific build system to use (auto-detect if None)
        
        Returns:
            Test command string
        """
        if not self.context:
            return ""

        if system_name:
            for bs in self.context.build_systems:
                if bs.name == system_name:
                    return bs.test_command
        else:
            # Auto-detect preferred build system
            priority = ["npm", "yarn", "pnpm", "cargo", "pip", "go", "make"]
            for preferred in priority:
                for bs in self.context.build_systems:
                    if bs.name == preferred:
                        return bs.test_command

        return ""
