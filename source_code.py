import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import networkx as nx
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import math
import heapq
import time


# ---------- Data container (undirected) ----------
class GraphData:
    def __init__(self, tag):
        self.tag = tag
        self.G = nx.Graph()
        self.sources = set()
        self.sinks = set()
        self.edge_tag = {}

    def clear(self):
        self.G.clear(); self.sources.clear(); self.sinks.clear(); self.edge_tag.clear()

    def add_edge(self, u, v, d, c, tag):
        self.G.add_edge(u, v, distance=float(d), cost=float(c))
        self.edge_tag[frozenset((u, v))] = tag

    def copy_from_combined(self, combined_graph, combined_edge_tag, sources, sinks, tag):
        self.clear()
        self.tag = tag
        for u, v, data in combined_graph.edges(data=True):
            self.G.add_edge(u, v, **data)
            self.edge_tag[frozenset((u, v))] = combined_edge_tag.get(frozenset((u, v)), tag)
        self.sources = set(sources)
        self.sinks = set(sinks)


# ---------- Canvas wrapper ----------
class GraphCanvas:
    def __init__(self, parent):
        self.fig = Figure(figsize=(5, 4))
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        self.G = None
        self.edge_tag = {}
        self.pos = {}
        self.node_colors = {}
        self.highlight_edges_map = {}
        self.edge_label_override = {}
        self.source_node = None
        self._dragging = None
        self._drag_offset = (0, 0)
        self.cid_press   = self.canvas.mpl_connect("button_press_event",   self._on_press)
        self.cid_release = self.canvas.mpl_connect("button_release_event", self._on_release)
        self.cid_motion  = self.canvas.mpl_connect("motion_notify_event",  self._on_motion)

    def _get_display_pos(self, xy):
        return self.ax.transData.transform(xy)

    def _get_data_pos(self, xdisp, ydisp):
        return self.ax.transData.inverted().transform((xdisp, ydisp))

    def _find_nearest_node(self, event, max_px=12):
        if event.inaxes != self.ax:
            return None
        best, best_dist = None, max_px + 1
        for n, p in self.pos.items():
            xd, yd = self._get_display_pos(p)
            d = math.hypot(xd - event.x, yd - event.y)
            if d < best_dist:
                best_dist = d; best = n
        return best if best_dist <= max_px else None

    def _on_press(self, event):
        node = self._find_nearest_node(event)
        if node is None: return
        self._dragging = node
        xdata = event.xdata if event.xdata is not None else self._get_data_pos(event.x, event.y)[0]
        ydata = event.ydata if event.ydata is not None else self._get_data_pos(event.x, event.y)[1]
        nxp, nyp = self.pos.get(node, (xdata, ydata))
        self._drag_offset = (nxp - xdata, nyp - ydata)

    def _on_motion(self, event):
        if self._dragging is None or event.inaxes != self.ax: return
        if event.xdata is None or event.ydata is None: return
        self.pos[self._dragging] = (event.xdata + self._drag_offset[0],
                                    event.ydata + self._drag_offset[1])
        self._draw_internal(); self.canvas.draw_idle()

    def _on_release(self, event):
        if self._dragging is None: return
        self._dragging = None; self._drag_offset = (0, 0)
        self._draw_internal(); self.canvas.draw_idle()

    def _draw_internal(self):
        self.ax.clear()
        if self.G is None or len(self.G.nodes) == 0:
            self.ax.text(0.5, 0.5, "Empty graph", ha='center')
            self.ax.set_axis_off(); return

        default = '#dddddd'
        colors = []
        for n in self.G.nodes():
            if self.source_node and n == self.source_node:
                colors.append('#00cc44')
            else:
                colors.append(self.node_colors.get(n, default) if self.node_colors else default)

        nx.draw_networkx_nodes(self.G, self.pos, node_color=colors, node_size=600, ax=self.ax)
        nx.draw_networkx_labels(self.G, self.pos, ax=self.ax)

        edge_colors, widths = [], []
        for u, v in self.G.edges():
            key = frozenset((u, v))
            tag = self.edge_tag.get(key, 'link')
            color = '#b3ffcc'
            if tag == 'g1':   color = '#9fc5ff'
            elif tag == 'g2': color = '#ffb3b3'
            w = 1.5

            in_dist = 'final_best'      in self.highlight_edges_map and key in self.highlight_edges_map['final_best']
            in_cost = 'final_best_cost' in self.highlight_edges_map and key in self.highlight_edges_map['final_best_cost']
            if in_dist and in_cost:
                color = '#8800cc'; w = 4.5
            elif in_dist:
                color = '#2255ff'; w = 4.5
            elif in_cost:
                color = '#cc0000'; w = 4.5
            elif 'path_chosen' in self.highlight_edges_map and key in self.highlight_edges_map['path_chosen']:
                color = '#00aa33'; w = 3.5
            elif 'considered'  in self.highlight_edges_map and key in self.highlight_edges_map['considered']:
                color = '#ffaa44'; w = 2.5
            elif 'final'       in self.highlight_edges_map and key in self.highlight_edges_map['final']:
                color = '#006400'; w = 4.5
            elif 'chosen'      in self.highlight_edges_map and key in self.highlight_edges_map['chosen']:
                color = '#2b7bff'; w = 4.0
            elif 'current'     in self.highlight_edges_map and key in self.highlight_edges_map['current']:
                color = '#8a2be2'; w = 4.0
            elif 'rejected'    in self.highlight_edges_map and key in self.highlight_edges_map['rejected']:
                color = '#d9534f'; w = 2.5

            edge_colors.append(color); widths.append(w)

        nx.draw_networkx_edges(self.G, self.pos, edge_color=edge_colors, width=widths, ax=self.ax)

        if self.edge_label_override:
            labels = {}
            for u, v in self.G.edges():
                key = frozenset((u, v))
                lbl = self.edge_label_override.get(key)
                labels[(u, v)] = lbl if lbl is not None else \
                    f"d={self.G[u][v].get('distance')},c={self.G[u][v].get('cost')}"
        else:
            labels = {(u, v): f"d={self.G[u][v].get('distance')},c={self.G[u][v].get('cost')}"
                      for u, v in self.G.edges()}

        nx.draw_networkx_edge_labels(self.G, self.pos, edge_labels=labels, font_size=8, ax=self.ax)
        self.ax.set_axis_off()

    def draw(self, G, edge_tag, node_colors=None, highlight_edges_map=None,
             external_pos=None, source_node=None, edge_label_override=None):
        self.G = G.copy() if G is not None else nx.Graph()
        self.edge_tag        = dict(edge_tag)   if edge_tag   else {}
        self.node_colors     = dict(node_colors) if node_colors else {}
        self.source_node     = source_node
        self.highlight_edges_map = {}
        for k, v in (highlight_edges_map or {}).items():
            self.highlight_edges_map[k] = set(frozenset(e) for e in v)

        self.edge_label_override = {}
        if edge_label_override:
            for k, v in edge_label_override.items():
                self.edge_label_override[k] = v

        nodes = list(self.G.nodes())
        if external_pos:
            for n, p in external_pos.items():
                if n in nodes and n not in self.pos:
                    self.pos[n] = p
        for n in list(self.pos.keys()):
            if n not in nodes: del self.pos[n]

        missing = [n for n in nodes if n not in self.pos]
        if missing:
            try:
                new_pos = nx.spring_layout(self.G, seed=42)
            except Exception:
                new_pos = {}
                k = len(nodes)
                for i, n in enumerate(nodes):
                    angle = 2 * math.pi * i / max(1, k)
                    new_pos[n] = (math.cos(angle), math.sin(angle))
            for n in missing:
                self.pos[n] = new_pos.get(n, (0.0, 0.0))

        self._draw_internal(); self.canvas.draw_idle()

    def clear_pos(self):
        self.pos = {}


# ---------- Utilities ----------
def build_combined(g1, g2, links):
    C = nx.Graph()
    edge_tag = {}
    for n in g1.G.nodes(): C.add_node(n)
    for n in g2.G.nodes(): C.add_node(n)
    for u, v, data in g1.G.edges(data=True):
        C.add_edge(u, v, **data); edge_tag[frozenset((u, v))] = 'g1'
    for u, v, data in g2.G.edges(data=True):
        C.add_edge(u, v, **data); edge_tag[frozenset((u, v))] = 'g2'
    for (u, v, d, c) in links:
        C.add_edge(u, v, distance=float(d), cost=float(c))
        edge_tag[frozenset((u, v))] = 'link'
    return C, edge_tag


def parse_edges_from_text(text):
    edges = []
    for line in text.splitlines():
        line = line.strip()
        if not line: continue
        parts = [p.strip() for p in line.split(',')]
        if len(parts) != 4:
            raise ValueError(f"Incorrect string format: {line}")
        u, v, d, c = parts
        edges.append((u.strip(), v.strip(), float(d), float(c)))
    return edges


def parse_graph_file(path):

    edges = []
    sources = set()
    sinks = set()
    links = []
    section = 'edges'

    for enc in ('utf-8', 'utf-8-sig', 'cp1251'):
        try:
            with open(path, 'r', encoding=enc) as f:
                raw = f.read()
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Failed to read file.")

    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith('#'): continue

        low = line.lower()
        if low.startswith('sources:'):
            section = 'sources'
            val = line.split(':', 1)[1].strip()
            if val:
                sources = set(s.strip() for s in val.split(',') if s.strip())
            continue
        elif low.startswith('sinks:'):
            section = 'sinks'
            val = line.split(':', 1)[1].strip()
            if val:
                sinks = set(s.strip() for s in val.split(',') if s.strip())
            continue
        elif low.startswith('links:'):
            section = 'links'
            val = line.split(':', 1)[1].strip()
            if val:
                parts = [p.strip() for p in val.split(',')]
                if len(parts) == 4:
                    links.append((parts[0], parts[1], float(parts[2]), float(parts[3])))
            continue
        elif low.startswith('edges:'):
            section = 'edges'
            continue

        if section == 'edges':
            parts = [p.strip() for p in line.split(',')]
            if len(parts) == 4:
                u, v, d, c = parts
                edges.append((u, v, float(d), float(c)))
        elif section == 'sources':
            sources.update(s.strip() for s in line.split(',') if s.strip())
        elif section == 'sinks':
            sinks.update(s.strip() for s in line.split(',') if s.strip())
        elif section == 'links':
            parts = [p.strip() for p in line.split(',')]
            if len(parts) == 4:
                links.append((parts[0], parts[1], float(parts[2]), float(parts[3])))

    return edges, sources, sinks, links


def validate_graph_connectivity(G):
    if len(G.nodes()) == 0:
        return True, ""
    if not nx.is_connected(G):
        components = list(nx.connected_components(G))
        return False, (f"The graph decomposes into {len(components)} component: "
                       + "; ".join("{" + ",".join(sorted(c)) + "}" for c in components))
    return True, ""


def validate_add_graph(existing_graph, new_edges, new_links):
    warnings = []
    errors = []

    if not new_edges:
        errors.append("The new graph does not contain any edges.")
        return False, warnings, errors

    new_G = nx.Graph()
    new_edge_keys = set()
    for u, v, d, c in new_edges:
        key = frozenset((u, v))
        if key in new_edge_keys:
            errors.append(f"Duplicate of the arc {u}-{v} in the new graph.")
        new_edge_keys.add(key)
        new_G.add_edge(u, v, distance=d, cost=c)

    ok_conn, conn_msg = validate_graph_connectivity(new_G)
    if not ok_conn:
        errors.append(f"The new graph is not connected: {conn_msg}")

    if errors:
        return False, warnings, errors

    if existing_graph and len(existing_graph.nodes()) > 0:
        existing_nodes = set(existing_graph.nodes())
        new_nodes      = set(new_G.nodes())

        shared_nodes = existing_nodes & new_nodes
        if shared_nodes:
            errors.append(
                "The new graph has vertices in common with the existing one — this means that they "
                "are already part of the same graph, not separate:\n"
                "  Shared vertices: " + ", ".join(sorted(shared_nodes)) + "\n"
                "Use the 'links:' section in the file to connect separate graphs."
            )

        shared_edges = []
        for u, v, d, c in new_edges:
            if existing_graph.has_edge(u, v):
                ex_d = existing_graph[u][v].get('distance')
                ex_c = existing_graph[u][v].get('cost')
                shared_edges.append(f"{u}-{v}(existing: d={ex_d},c={ex_c}; new: d={d},c={c})")
        if shared_edges:
            errors.append(
                "The following arcs of the new graph already exist in the existing one:\n  " +
                "\n  ".join(shared_edges)
            )

    if errors:
        return False, warnings, errors

    if existing_graph and len(existing_graph.nodes()) > 0:
        existing_nodes = set(existing_graph.nodes())
        new_nodes      = set(new_G.nodes())

        for u, v, d, c in new_links:
            u_in_ex  = u in existing_nodes
            u_in_new = u in new_nodes
            v_in_ex  = v in existing_nodes
            v_in_new = v in new_nodes

            if u_in_ex and v_in_ex:
                errors.append(
                    f"З'єднувальна дуга {u}-{v}: обидві вершини належать існуючому графу. "
                    "Links мають з'єднувати існуючий граф з новим."
                )
            elif u_in_new and v_in_new:
                errors.append(
                    f"З'єднувальна дуга {u}-{v}: обидві вершини належать новому графу. "
                    "Links мають з'єднувати існуючий граф з новим."
                )
            elif not ((u_in_ex and v_in_new) or (u_in_new and v_in_ex)):
                errors.append(
                    f"З'єднувальна дуга {u}-{v}: одна або обидві вершини "
                    "не знайдені ні в існуючому, ні в новому графі."
                )

            if existing_graph.has_edge(u, v):
                errors.append(f"З'єднувальна дуга {u}-{v} вже існує в графі.")

    elif new_links:
        warnings.append("Links вказані, але існуючий граф порожній — links будуть проігноровані.")

    return len(errors) == 0, warnings, errors


def validate_remove_graph(current_graph, remove_edges, current_links=None):
    warnings = []
    errors = []

    if not remove_edges:
        errors.append("Файл не містить жодної дуги для вилучення.")
        return False, warnings, errors

    missing = []
    for u, v, d, c in remove_edges:
        if not current_graph.has_edge(u, v):
            missing.append(f"{u}-{v}")
    if missing:
        errors.append(
            "Наступних дуг немає в поточному графі: " + ", ".join(missing) + ".\n"
            "Вилучення неможливе."
        )
        return False, warnings, errors

    test_G = current_graph.copy()
    for u, v, d, c in remove_edges:
        if test_G.has_edge(u, v):
            test_G.remove_edge(u, v)

    isolated = list(nx.isolates(test_G))
    if isolated:
        warnings.append(
            "Після вилучення з'являться ізольовані вершини: " +
            ", ".join(sorted(isolated)) + " — їх буде видалено автоматично."
        )
        test_G.remove_nodes_from(isolated)

    if len(test_G.nodes()) > 1:
        if not nx.is_connected(test_G):
            components = list(nx.connected_components(test_G))
            comp_str   = "; ".join(
                "{" + ", ".join(sorted(c)) + "}" for c in components
            )
            errors.append(
                f"Вилучення розіб'є граф на {len(components)} непов'язані частини:\n"
                f"  {comp_str}\n"
                "Вилучення заборонено — граф не повинен розпадатися на відрізки."
            )
            return False, warnings, errors

    return True, warnings, errors


# ---------- Step builder: Shortest Path ----------
def build_steps_for_pair(graph, s, t, weight_attr='distance'):
    steps = []
    step_idx = [0]

    if s not in graph.nodes() or t not in graph.nodes():
        steps.append({'desc': f"Пара {s} -> {t}: одна з вершин відсутня в графі.",
                      'highlight': {}, 'source_node': None, 'edge_label_override': None})
        return steps

    criterion_label = 'відстань' if weight_attr == 'distance' else 'вартість'

    def get_weight(u, v):
        return graph[u][v].get(weight_attr, 1.0)

    def edge_label(u, v):
        w = get_weight(u, v)
        attr = 'відстань' if weight_attr == 'distance' else 'вартість'
        return f"{u}-{v} ({attr}={w})"

    def record(desc, path_chosen=None, considered=None, source_active=True,
               final_key=None, final_edges=None):
        step_idx[0] += 1
        hm = {}
        if path_chosen:
            hm['path_chosen'] = set(frozenset(e) for e in path_chosen)
        if considered:
            hm['considered'] = set(frozenset(e) for e in considered)
        if final_edges and final_key:
            hm[final_key] = set(frozenset(e) for e in final_edges)
        steps.append({'desc': f"Крок {step_idx[0]}: {desc}",
                      'highlight': hm,
                      'source_node': s if source_active else None,
                      'edge_label_override': None})

    all_paths = []

    def enumerate_paths(current, path_nodes, path_edges, current_dist):
        neighbors = sorted(
            [(nb, get_weight(current, nb)) for nb in graph.neighbors(current)
             if nb not in path_nodes],
            key=lambda x: x[1]
        )
        for nb, w in neighbors:
            new_nodes = path_nodes + [nb]
            new_edges = path_edges + [(current, nb)]
            new_dist  = current_dist + w
            if nb == t:
                all_paths.append((new_nodes, new_edges, new_dist))
            else:
                enumerate_paths(nb, new_nodes, new_edges, new_dist)

    enumerate_paths(s, [s], [], 0.0)

    record(f"Позначаємо джерело {s}. Починаємо пошук шляху до {t}.")

    if not all_paths:
        step_idx[0] += 1
        steps.append({'desc': f"Крок {step_idx[0]}: Шлях від {s} до {t} не знайдено.",
                      'highlight': {}, 'source_node': None, 'edge_label_override': None})
        return steps

    best_paths = []
    best_dist  = math.inf

    for path_idx, (path_nodes, path_edges, path_dist) in enumerate(all_paths):
        for step_i, (u, v) in enumerate(path_edges):
            visited = set(path_nodes[:step_i + 1])
            avail_neighbors = sorted(
                [(nb, get_weight(u, nb)) for nb in graph.neighbors(u)
                 if nb not in visited],
                key=lambda x: x[1]
            )
            avail_edges  = [(u, nb) for (nb, _) in avail_neighbors]
            green_edges  = list(path_edges[:step_i])
            avail_labels = ", ".join(edge_label(u, nb) for (nb, _) in avail_neighbors)
            record(f"У вершині {u}. Доступні дуги: {avail_labels}.",
                   path_chosen=green_edges, considered=avail_edges, source_active=True)

            dist_so_far    = sum(get_weight(path_nodes[j], path_nodes[j + 1])
                                 for j in range(step_i + 1))
            green_edges_new = list(path_edges[:step_i + 1])
            remaining_orange = [(u, nb) for (nb, _) in avail_neighbors if nb != v]
            record(f"Обираємо дугу {edge_label(u, v)}. Поточна {criterion_label}: {dist_so_far}.",
                   path_chosen=green_edges_new,
                   considered=remaining_orange if remaining_orange else None,
                   source_active=True)

        edge_str = " -> ".join(
            f"{path_nodes[i]}-{path_nodes[i + 1]}" for i in range(len(path_nodes) - 1)
        )

        if path_dist < best_dist:
            if not best_paths:
                comment = "Це перший знайдений шлях — приймаємо як найкращий."
            else:
                old_str = " -> ".join(f"{best_paths[0][i]}-{best_paths[0][i+1]}"
                                      for i in range(len(best_paths[0]) - 1))
                comment = (f"Кращий за попередній {old_str} "
                           f"({criterion_label}={best_dist}). Оновлюємо найкращий шлях.")
            best_paths = [path_nodes]
            best_dist  = path_dist
            step_idx[0] += 1
            steps.append({
                'desc': (f"Крок {step_idx[0]}: Знайдено шлях {edge_str}, "
                         f"{criterion_label} = {path_dist}. {comment}"),
                'highlight': {'path_chosen': set(frozenset(e) for e in path_edges)},
                'source_node': s, 'edge_label_override': None})
        elif path_dist == best_dist:
            best_paths.append(path_nodes)
            all_best_str = "; ".join(
                " -> ".join(f"{bp[i]}-{bp[i+1]}" for i in range(len(bp)-1))
                for bp in best_paths[:-1]
            )
            step_idx[0] += 1
            steps.append({
                'desc': (f"Крок {step_idx[0]}: Знайдено шлях {edge_str}, "
                         f"{criterion_label} = {path_dist}. "
                         f"Однаково оптимальний з: {all_best_str}. Додаємо до найкращих."),
                'highlight': {'path_chosen': set(frozenset(e) for e in path_edges)},
                'source_node': s, 'edge_label_override': None})
        else:
            best_str = " -> ".join(f"{best_paths[0][i]}-{best_paths[0][i+1]}"
                                   for i in range(len(best_paths[0]) - 1))
            step_idx[0] += 1
            steps.append({
                'desc': (f"Крок {step_idx[0]}: Знайдено шлях {edge_str}, "
                         f"{criterion_label} = {path_dist}. "
                         f"Не кращий за {best_str} ({criterion_label}={best_dist}), відкидаємо."),
                'highlight': {}, 'source_node': s, 'edge_label_override': None})

        if path_idx < len(all_paths) - 1:
            record(f"Повертаємось до джерела {s}. Шукаємо наступний шлях.",
                   path_chosen=None, considered=None, source_active=True)

    if best_paths:
        final_key = 'final_best' if weight_attr == 'distance' else 'final_best_cost'
        all_best_edges = set()
        for bp in best_paths:
            for i in range(len(bp) - 1):
                all_best_edges.add(frozenset((bp[i], bp[i + 1])))

        if len(best_paths) == 1:
            bp       = best_paths[0]
            best_str = " -> ".join(f"{bp[i]}-{bp[i+1]}" for i in range(len(bp)-1))
            desc     = (f"Крок {step_idx[0] + 1}: Всі шляхи розглянуто. "
                        f"Найкращий шлях: {best_str}, {criterion_label} = {best_dist}.")
        else:
            paths_str = "\n  ".join(
                f"{j+1}) " + " -> ".join(f"{bp[i]}-{bp[i+1]}" for i in range(len(bp)-1))
                for j, bp in enumerate(best_paths)
            )
            desc = (f"Крок {step_idx[0] + 1}: Всі шляхи розглянуто. "
                    f"Знайдено {len(best_paths)} однаково оптимальних шляхи "
                    f"({criterion_label} = {best_dist}):\n  {paths_str}")

        step_idx[0] += 1
        steps.append({'desc': desc,
                      'highlight': {final_key: all_best_edges},
                      'source_node': None, 'edge_label_override': None})

    return steps


# ---------- Step builder: Ford-Fulkerson ----------
def build_ff_steps(graph, s, t, weight_attr='distance'):
    steps     = []
    step_idx  = [0]
    attr_label = 'відстань' if weight_attr == 'distance' else 'вартість'

    if s not in graph.nodes() or t not in graph.nodes():
        steps.append({'desc': f"(ФФ) {s} -> {t}: одна з вершин відсутня в графі.",
                      'highlight': {}, 'source_node': None, 'edge_label_override': None})
        return steps, 0.0

    if s == t:
        steps.append({'desc': f"(ФФ) {s} -> {t}: джерело і стік співпадають.",
                      'highlight': {}, 'source_node': None, 'edge_label_override': None})
        return steps, 0.0

    residual = nx.DiGraph()
    for node in graph.nodes():
        residual.add_node(node)

    original_cap = {}
    for u, v, data in graph.edges(data=True):
        cap = float(data.get(weight_attr, 1.0))
        key = frozenset((u, v))
        original_cap[key] = cap
        residual.add_edge(u, v, capacity=cap)
        residual.add_edge(v, u, capacity=cap)

    directed_flow = {}
    for u, v in graph.edges():
        directed_flow[(u, v)] = 0.0
        directed_flow[(v, u)] = 0.0

    def get_edge_labels():
        labels = {}
        for u, v in graph.edges():
            key  = frozenset((u, v))
            cap  = original_cap.get(key, 1.0)
            net  = directed_flow.get((u, v), 0.0) - directed_flow.get((v, u), 0.0)
            used = abs(net)
            remaining = max(0.0, cap - used)
            labels[key] = f"{remaining:.0f}/{used:.0f}"
        return labels

    def widest_path_search(res, src, tgt):
        best_bn = {node: 0.0 for node in res.nodes()}
        best_bn[src] = float('inf')
        prev    = {src: None}
        heap    = [(-float('inf'), src)]
        visited = set()

        while heap:
            neg_b, u = heapq.heappop(heap)
            b = -neg_b
            if u in visited: continue
            visited.add(u)
            if u == tgt: break
            for v in res.successors(u):
                if v not in visited:
                    cap = res[u][v].get('capacity', 0.0)
                    if cap > 0:
                        new_b = min(b, cap)
                        if new_b > best_bn[v]:
                            best_bn[v] = new_b
                            prev[v] = u
                            heapq.heappush(heap, (-new_b, v))

        if best_bn.get(tgt, 0) == 0:
            return None, 0.0

        path = []
        node = tgt
        while node is not None:
            path.append(node)
            node = prev.get(node)
        path.reverse()

        if not path or path[0] != src:
            return None, 0.0
        return path, best_bn[tgt]

    total_flow = 0.0
    all_used_edges = set()
    iter_flows = []

    step_idx[0] += 1
    steps.append({
        'desc': (f"Крок {step_idx[0]}: Ініціалізація алгоритму Форда-Фалкерсона. "
                 f"Джерело: {s}, стік: {t}. "
                 f"Критерій ({attr_label}) використовується як пропускна здатність."),
        'highlight': {},
        'source_node': s,
        'edge_label_override': get_edge_labels()
    })

    while True:
        path, bn_val = widest_path_search(residual, s, t)
        if path is None or bn_val == 0:
            break

        path_edges_list    = [(path[i], path[i+1]) for i in range(len(path) - 1)]
        path_edge_fs       = set(frozenset(e) for e in path_edges_list)
        path_str           = " -> ".join(path)

        step_idx[0] += 1
        steps.append({
            'desc': (f"Крок {step_idx[0]}: Обираємо шлях: {path_str}."),
            'highlight': {'considered': path_edge_fs},
            'source_node': s,
            'edge_label_override': get_edge_labels()
        })

        bottleneck_edge = None
        min_cap_val     = float('inf')
        for u, v in path_edges_list:
            cap = residual[u][v]['capacity']
            if cap < min_cap_val:
                min_cap_val     = cap
                bottleneck_edge = (u, v)

        f = min_cap_val

        for u, v in path_edges_list:
            residual[u][v]['capacity'] -= f
            if residual.has_edge(v, u):
                residual[v][u]['capacity'] += f
            else:
                residual.add_edge(v, u, capacity=f)

        for u, v in path_edges_list:
            directed_flow[(u, v)] = directed_flow.get((u, v), 0.0) + f
            all_used_edges.add(frozenset((u, v)))

        iter_flows.append(f)
        total_flow += f

        bn_str = f"{bottleneck_edge[0]}-{bottleneck_edge[1]}" if bottleneck_edge else "?"
        step_idx[0] += 1
        steps.append({
            'desc': (f"Крок {step_idx[0]}: Вузьке місце — {bn_str} ({attr_label} = {f:.0f}). "
                     f"Пропускаємо {f:.0f} та оновлюємо залишки."),
            'highlight': {'path_chosen': path_edge_fs},
            'source_node': s,
            'edge_label_override': get_edge_labels()
        })

        if len(iter_flows) == 1:
            flow_sum_str = f"{iter_flows[0]:.0f}"
        else:
            parts        = " + ".join(f"{x:.0f}" for x in iter_flows)
            flow_sum_str = f"{parts} = {total_flow:.0f}"

        step_idx[0] += 1
        steps.append({
            'desc': f"Крок {step_idx[0]}: Записуємо пропущений потік: v = {flow_sum_str}.",
            'highlight': {'path_chosen': path_edge_fs},
            'source_node': s,
            'edge_label_override': get_edge_labels()
        })

    step_idx[0] += 1
    if total_flow == 0:
        desc = (f"Крок {step_idx[0]}: Алгоритм завершено. "
                f"Шлях від {s} до {t} не знайдено. Максимальний потік = 0.")
    else:
        parts        = " + ".join(f"{x:.0f}" for x in iter_flows)
        flow_sum_str = f"{parts} = {total_flow:.0f}" if len(iter_flows) > 1 else f"{total_flow:.0f}"
        desc = (f"Крок {step_idx[0]}: Алгоритм завершено. "
                f"Максимальний потік від {s} до {t}: v = {flow_sum_str}.")

    steps.append({
        'desc': desc,
        'highlight': {'final': all_used_edges} if all_used_edges else {},
        'source_node': None,
        'edge_label_override': get_edge_labels()
    })

    return steps, total_flow


# ---------- Pure FF computation ----------
def run_ff_compute(graph, s, t, weight_attr='distance'):
    if s not in graph.nodes() or t not in graph.nodes() or s == t:
        return 0.0, set(), {}

    residual = nx.DiGraph()
    for node in graph.nodes():
        residual.add_node(node)
    for u, v, data in graph.edges(data=True):
        cap = float(data.get(weight_attr, 1.0))
        residual.add_edge(u, v, capacity=cap)
        residual.add_edge(v, u, capacity=cap)

    directed_flow = {}
    for u, v in graph.edges():
        directed_flow[(u, v)] = 0.0
        directed_flow[(v, u)] = 0.0

    def widest_path_search(res, src, tgt):
        best_bn = {node: 0.0 for node in res.nodes()}
        best_bn[src] = float('inf')
        prev    = {src: None}
        heap    = [(-float('inf'), src)]
        visited = set()
        while heap:
            neg_b, u = heapq.heappop(heap)
            b = -neg_b
            if u in visited: continue
            visited.add(u)
            if u == tgt: break
            for v in res.successors(u):
                if v not in visited:
                    cap = res[u][v].get('capacity', 0.0)
                    if cap > 0:
                        new_b = min(b, cap)
                        if new_b > best_bn[v]:
                            best_bn[v] = new_b; prev[v] = u
                            heapq.heappush(heap, (-new_b, v))
        if best_bn.get(tgt, 0) == 0:
            return None, 0.0
        path = []
        node = tgt
        while node is not None:
            path.append(node); node = prev.get(node)
        path.reverse()
        if not path or path[0] != src:
            return None, 0.0
        return path, best_bn[tgt]

    total_flow     = 0.0
    all_used_edges = set()

    while True:
        path, bn_val = widest_path_search(residual, s, t)
        if path is None or bn_val == 0:
            break
        path_edges = [(path[i], path[i+1]) for i in range(len(path) - 1)]
        f = bn_val
        for u, v in path_edges:
            residual[u][v]['capacity'] -= f
            if residual.has_edge(v, u):
                residual[v][u]['capacity'] += f
            else:
                residual.add_edge(v, u, capacity=f)
            directed_flow[(u, v)] = directed_flow.get((u, v), 0.0) + f
            all_used_edges.add(frozenset((u, v)))
        total_flow += f

    return total_flow, all_used_edges, directed_flow


# ---------- Main App ----------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Graph Viewer")
        self.geometry("1400x850")
        self.g1 = GraphData('g1')
        self.g2 = GraphData('g2')
        self.links          = []
        self.combined_graph = None
        self.combined_tag   = {}
        self.steps          = []
        self.step_index     = -1
        self._sp_elapsed    = None
        self._ff_elapsed    = None
        self._history = []
        self._build_ui()
        self.redraw_all()

    # ─────────────────────────────────────────────────────────────────────────
    # UI Construction
    # ─────────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        main = ttk.Frame(self); main.pack(fill='both', expand=True)

        left_outer = ttk.Frame(main, width=460); left_outer.pack(side='left', fill='y')
        left_outer.pack_propagate(False)

        left_canvas = tk.Canvas(left_outer, borderwidth=0, highlightthickness=0)
        left_scroll = ttk.Scrollbar(left_outer, orient='vertical', command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_scroll.pack(side='right', fill='y')
        left_canvas.pack(side='left', fill='both', expand=True)

        left = ttk.Frame(left_canvas)
        left_window = left_canvas.create_window((0, 0), window=left, anchor='nw')

        def _on_left_configure(event):
            left_canvas.configure(scrollregion=left_canvas.bbox('all'))
        def _on_canvas_resize(event):
            left_canvas.itemconfig(left_window, width=event.width)
        left.bind('<Configure>', _on_left_configure)
        left_canvas.bind('<Configure>', _on_canvas_resize)

        def _on_mousewheel(event):
            left_canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        left_canvas.bind_all('<MouseWheel>', _on_mousewheel)

        right = ttk.Frame(main); right.pack(side='right', fill='both', expand=True)

        # ── Graph 1 ──────────────────────────────────────────────────────────
        ttk.Label(left, text="Graph 1 edges (u,v,distance,cost)").pack(anchor='w', padx=5, pady=2)
        self.g1_text = tk.Text(left, height=5); self.g1_text.pack(fill='x', padx=5)
        ttk.Label(left, text="Sources (comma)").pack(anchor='w', padx=5)
        self.g1_src = ttk.Entry(left); self.g1_src.pack(fill='x', padx=5)
        ttk.Label(left, text="Sinks (comma)").pack(anchor='w', padx=5)
        self.g1_sink = ttk.Entry(left); self.g1_sink.pack(fill='x', padx=5)

        g1_btn_frame = ttk.Frame(left); g1_btn_frame.pack(fill='x', padx=5, pady=3)
        ttk.Button(g1_btn_frame, text="Load G1", command=self.load_g1).pack(side='left', expand=True, fill='x', padx=(0,2))
        ttk.Button(g1_btn_frame, text="Load G1 from file", command=self.load_g1_file).pack(side='left', expand=True, fill='x', padx=(2,0))

        # ── Graph 2 ──────────────────────────────────────────────────────────
        ttk.Label(left, text="Graph 2 edges (u,v,distance,cost)").pack(anchor='w', padx=5, pady=2)
        self.g2_text = tk.Text(left, height=5); self.g2_text.pack(fill='x', padx=5)
        ttk.Label(left, text="Sources (comma)").pack(anchor='w', padx=5)
        self.g2_src = ttk.Entry(left); self.g2_src.pack(fill='x', padx=5)
        ttk.Label(left, text="Sinks (comma)").pack(anchor='w', padx=5)
        self.g2_sink = ttk.Entry(left); self.g2_sink.pack(fill='x', padx=5)

        g2_btn_frame = ttk.Frame(left); g2_btn_frame.pack(fill='x', padx=5, pady=3)
        ttk.Button(g2_btn_frame, text="Load G2", command=self.load_g2).pack(side='left', expand=True, fill='x', padx=(0,2))
        ttk.Button(g2_btn_frame, text="Load G2 from file", command=self.load_g2_file).pack(side='left', expand=True, fill='x', padx=(2,0))

        # ── Links ─────────────────────────────────────────────────────────────
        ttk.Label(left, text="Links (sink G1 → source G2)").pack(anchor='w', padx=5, pady=2)
        self.links_text = tk.Text(left, height=3); self.links_text.pack(fill='x', padx=5)
        lnk_btn_frame = ttk.Frame(left); lnk_btn_frame.pack(fill='x', padx=5, pady=3)
        ttk.Button(lnk_btn_frame, text="Add Links", command=self.add_links).pack(side='left', expand=True, fill='x', padx=(0,2))
        ttk.Button(lnk_btn_frame, text="Links from file", command=self.load_links_file).pack(side='left', expand=True, fill='x', padx=(2,0))

        ttk.Separator(left, orient='horizontal').pack(fill='x', padx=5, pady=6)

        # ── Recursive graph operations ────────────────────────────────────────
        rec_lbl = ttk.Label(left, text="Recursive graph management",
                            font=('', 10, 'bold'))
        rec_lbl.pack(anchor='w', padx=5)

        ttk.Label(left,
                  text="New graph file (edges + sources: + sinks: + links:)",
                  wraplength=420, justify='left').pack(anchor='w', padx=5, pady=(2,0))

        add_rm_frame = ttk.Frame(left); add_rm_frame.pack(fill='x', padx=5, pady=3)
        ttk.Button(add_rm_frame, text="➕  Add a graph from a file",
                   command=self.add_graph_from_file).pack(side='left', expand=True, fill='x', padx=(0,2))
        ttk.Button(add_rm_frame, text="➖  Remove graph from file",
                   command=self.remove_graph_from_file).pack(side='left', expand=True, fill='x', padx=(2,0))

        ttk.Button(left, text="↩  Undo last operation",
                   command=self.undo_last).pack(fill='x', padx=5, pady=(0, 6))

        ttk.Separator(left, orient='horizontal').pack(fill='x', padx=5, pady=4)

        # ── Algorithm ─────────────────────────────────────────────────────────
        ttk.Label(left, text="Algorithm", font=('', 10, 'bold')).pack(anchor='w', padx=5)
        self.algorithm_var = tk.StringVar(value='shortest_path')
        ttk.Radiobutton(left, text="The shortest path (SP)",
                        variable=self.algorithm_var, value='shortest_path').pack(anchor='w', padx=15)
        ttk.Radiobutton(left, text="Ford-Fulkerson (FF)",
                        variable=self.algorithm_var, value='ford_fulkerson').pack(anchor='w', padx=15)

        ttk.Separator(left, orient='horizontal').pack(fill='x', padx=5, pady=4)
        ttk.Label(left, text="Criterion", font=('', 10, 'bold')).pack(anchor='w', padx=5)
        self.criterion_var = tk.StringVar(value='distance')
        ttk.Radiobutton(left, text="distance", variable=self.criterion_var, value='distance').pack(anchor='w', padx=15)
        ttk.Radiobutton(left, text="cost",     variable=self.criterion_var, value='cost').pack(anchor='w', padx=15)

        ttk.Separator(left, orient='horizontal').pack(fill='x', padx=5, pady=4)

        calc_frame = ttk.Frame(left); calc_frame.pack(fill='x', padx=5, pady=2)
        ttk.Button(calc_frame, text="Compute (fast)",
                   command=self.compute_fast).pack(side='left', expand=True, fill='x', padx=(0,2))
        ttk.Button(calc_frame, text="Compute (step-by-step)",
                   command=self.compute_step).pack(side='left', expand=True, fill='x', padx=(2,0))
        ttk.Button(left, text="Compare speed (SP vs FF)",
                   command=self.compare_speed).pack(padx=5, pady=(0, 4), fill='x')

        nav = ttk.Frame(left); nav.pack(fill='x', padx=5, pady=(0, 4))
        self.btn_back    = ttk.Button(nav, text="←  Back",  command=self.step_back)
        self.btn_forward = ttk.Button(nav, text="Forward  →", command=self.step_forward)
        self.btn_back.pack(side='left',  expand=True, fill='x', padx=(0, 4))
        self.btn_forward.pack(side='left', expand=True, fill='x', padx=(4, 0))
        self.step_label = ttk.Label(left, text="Step: 0 / 0")
        self.step_label.pack(anchor='w', padx=5)

        ttk.Label(left, text="Graph information / Steps").pack(anchor='w', padx=5, pady=2)
        self.info_box = tk.Text(left, height=22, wrap='word')
        self.info_box.pack(fill='both', padx=5, pady=2, expand=True)

        self.notebook = ttk.Notebook(right); self.notebook.pack(fill='both', expand=True)
        tab1 = ttk.Frame(self.notebook); self.notebook.add(tab1, text="Graph 1")
        self.canvas1 = GraphCanvas(tab1)
        tab2 = ttk.Frame(self.notebook); self.notebook.add(tab2, text="Graph 2")
        self.canvas2 = GraphCanvas(tab2)
        tab3 = ttk.Frame(self.notebook); self.notebook.add(tab3, text="Combined")
        self.canvas3 = GraphCanvas(tab3)

    # ─────────────────────────────────────────────────────────────────────────
    # Snapshot / Undo
    # ─────────────────────────────────────────────────────────────────────────
    def _take_snapshot(self):
        def snap_gdata(gd):
            g_copy = gd.G.copy()
            return {
                'G': g_copy,
                'sources': set(gd.sources),
                'sinks': set(gd.sinks),
                'edge_tag': dict(gd.edge_tag),
                'tag': gd.tag,
            }
        self._history.append({
            'g1': snap_gdata(self.g1),
            'g2': snap_gdata(self.g2),
            'links': list(self.links),
            'g1_text': self.g1_text.get("1.0", "end"),
            'g2_text': self.g2_text.get("1.0", "end"),
            'g1_src': self.g1_src.get(),
            'g1_sink': self.g1_sink.get(),
            'g2_src': self.g2_src.get(),
            'g2_sink': self.g2_sink.get(),
        })

    def _restore_snapshot(self, snap):
        def restore_gdata(gd, s):
            gd.clear()
            gd.tag = s['tag']
            for u, v, data in s['G'].edges(data=True):
                gd.G.add_edge(u, v, **data)
            gd.sources = set(s['sources'])
            gd.sinks   = set(s['sinks'])
            gd.edge_tag = dict(s['edge_tag'])
        restore_gdata(self.g1, snap['g1'])
        restore_gdata(self.g2, snap['g2'])
        self.links = list(snap['links'])
        self.g1_text.delete("1.0", "end"); self.g1_text.insert("1.0", snap['g1_text'])
        self.g2_text.delete("1.0", "end"); self.g2_text.insert("1.0", snap['g2_text'])
        self.g1_src.delete(0, 'end');  self.g1_src.insert(0, snap['g1_src'])
        self.g1_sink.delete(0, 'end'); self.g1_sink.insert(0, snap['g1_sink'])
        self.g2_src.delete(0, 'end');  self.g2_src.insert(0, snap['g2_src'])
        self.g2_sink.delete(0, 'end'); self.g2_sink.insert(0, snap['g2_sink'])

    def undo_last(self):
        if not self._history:
            messagebox.showinfo("Скасування", "Немає операцій для скасування.")
            return
        snap = self._history.pop()
        self._restore_snapshot(snap)
        self._refresh_links_text()
        self._update_info()
        self.redraw_all()
        messagebox.showinfo("Скасування", "Останню операцію скасовано.")

    # ─────────────────────────────────────────────────────────────────────────
    # Recursive Add / Remove
    # ─────────────────────────────────────────────────────────────────────────
    def add_graph_from_file(self):
        path = filedialog.askopenfilename(
            title="Оберіть файл нового графу",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not path: return

        try:
            new_edges, new_sources, new_sinks, new_links = parse_graph_file(path)
        except Exception as e:
            messagebox.showerror("Помилка читання файлу", str(e)); return

        if not new_edges:
            messagebox.showwarning("Порожній файл", "Файл не містить дуг."); return

        g1_empty = len(self.g1.G.nodes()) == 0
        g2_empty = len(self.g2.G.nodes()) == 0

        if g1_empty:
            new_G = nx.Graph()
            for u, v, d, c in new_edges:
                new_G.add_edge(u, v, distance=d, cost=c)
            ok_conn, conn_msg = validate_graph_connectivity(new_G)
            if not ok_conn:
                messagebox.showerror("Некоректний граф",
                                     f"Новий граф не є зв'язним:\n{conn_msg}")
                return

            self._take_snapshot()
            self.g1.clear()
            for u, v, d, c in new_edges:
                self.g1.add_edge(u, v, d, c, 'g1')
            self.g1.sources = set(new_sources)
            self.g1.sinks   = set(new_sinks)
            self._sync_g1_ui()
            self._update_info(); self.redraw_all()
            messagebox.showinfo("Граф додано", "Граф завантажено як Graph 1.")

        elif g2_empty:
            ok, warns, errs = validate_add_graph(self.g1.G, new_edges, new_links)
            if errs:
                messagebox.showerror("Помилки валідації",
                                     "Неможливо додати граф:\n\n" + "\n".join(errs))
                return
            if warns:
                if not messagebox.askyesno("Попередження",
                                           "\n".join(warns) + "\n\nПродовжити?"):
                    return

            self._take_snapshot()
            self.g2.clear()
            for u, v, d, c in new_edges:
                self.g2.add_edge(u, v, d, c, 'g2')
            self.g2.sources = set(new_sources)
            self.g2.sinks   = set(new_sinks)
            for lnk in new_links:
                self.links.append(lnk)
            self._sync_g2_ui()
            self._refresh_links_text()
            self._update_info(); self.redraw_all()
            messagebox.showinfo("Граф додано", "Граф завантажено як Graph 2.")

        else:
            C_cur, C_tag = build_combined(self.g1, self.g2, self.links)

            ok, warns, errs = validate_add_graph(C_cur, new_edges, new_links)
            if errs:
                messagebox.showerror("Помилки валідації",
                                     "Неможливо додати граф:\n\n" + "\n".join(errs))
                return
            if warns:
                if not messagebox.askyesno("Попередження",
                                           "\n".join(warns) + "\n\nПродовжити?"):
                    return

            self._take_snapshot()

            old_sources = set(self.g1.sources)
            old_sinks   = set(self.g2.sinks)

            self.g1.clear()
            self.g1.tag = 'g1'
            for u, v, data in C_cur.edges(data=True):
                self.g1.G.add_edge(u, v, **data)
                self.g1.edge_tag[frozenset((u, v))] = 'g1'
            self.g1.sources = old_sources
            self.g1.sinks   = old_sinks

            self.g2.clear()
            self.g2.tag = 'g2'
            for u, v, d, c in new_edges:
                self.g2.add_edge(u, v, d, c, 'g2')
            self.g2.sources = set(new_sources)
            self.g2.sinks   = set(new_sinks)

            self.links = list(new_links)

            self._sync_g1_ui()
            self._sync_g2_ui()
            self._refresh_links_text()
            self.canvas1.clear_pos()
            self.canvas2.clear_pos()
            self.canvas3.clear_pos()
            self._update_info(); self.redraw_all()
            messagebox.showinfo(
                "Граф додано",
                "Попередній об'єднаний граф (G1+G2+Links) став Graph 1.\n"
                "Новий граф з файлу став Graph 2.\n"
                "Графи з'єднані лише через вказані links."
            )

    def remove_graph_from_file(self):
        path = filedialog.askopenfilename(
            title="Оберіть файл графу для вилучення",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not path: return

        try:
            rm_edges, rm_sources, rm_sinks, rm_links = parse_graph_file(path)
        except Exception as e:
            messagebox.showerror("Помилка читання файлу", str(e)); return

        if not rm_edges and not rm_links:
            messagebox.showwarning("Порожній файл", "Файл не містить дуг для вилучення.")
            return

        C_cur, C_tag = build_combined(self.g1, self.g2, self.links)

        links_to_remove = []
        if rm_links:
            for u, v, d, c in rm_links:
                for lnk in self.links:
                    if frozenset((lnk[0], lnk[1])) == frozenset((u, v)):
                        if lnk not in links_to_remove:
                            links_to_remove.append(lnk)

        all_rm = list(rm_edges) + [(u, v, d, c) for u, v, d, c in rm_links]

        ok, warns, errs = validate_remove_graph(C_cur, all_rm if all_rm else rm_edges,
                                                current_links=self.links)
        if errs:
            messagebox.showerror("Вилучення неможливе", "\n".join(errs))
            return
        if warns:
            if not messagebox.askyesno("Попередження", "\n".join(warns) + "\n\nПродовжити?"):
                return

        self._take_snapshot()

        removed_edges = 0
        for u, v, d, c in rm_edges:
            if self.g1.G.has_edge(u, v):
                self.g1.G.remove_edge(u, v)
                self.g1.edge_tag.pop(frozenset((u, v)), None)
                removed_edges += 1
            elif self.g2.G.has_edge(u, v):
                self.g2.G.remove_edge(u, v)
                self.g2.edge_tag.pop(frozenset((u, v)), None)
                removed_edges += 1

        removed_links = 0
        for lnk in links_to_remove:
            if lnk in self.links:
                self.links.remove(lnk)
                removed_links += 1

        for n in list(nx.isolates(self.g1.G)):
            self.g1.G.remove_node(n)
            self.g1.sources.discard(n); self.g1.sinks.discard(n)
        for n in list(nx.isolates(self.g2.G)):
            self.g2.G.remove_node(n)
            self.g2.sources.discard(n); self.g2.sinks.discard(n)

        if rm_sources:
            self.g1.sources -= rm_sources; self.g2.sources -= rm_sources
        if rm_sinks:
            self.g1.sinks   -= rm_sinks;   self.g2.sinks   -= rm_sinks

        if removed_edges == 0 and removed_links == 0:
            self._history.pop()
            messagebox.showwarning("Нічого не вилучено",
                                   "Жодної дуги зі вказаного файлу не знайдено в поточному графі.")
            return

        self._sync_g1_ui()
        self._sync_g2_ui()
        self._refresh_links_text()
        self._update_info()
        self.redraw_all()
        messagebox.showinfo(
            "Вилучення виконано",
            f"Вилучено: {removed_edges} дуг(и), {removed_links} з'єднань (links)."
        )

    # ─────────────────────────────────────────────────────────────────────────
    # UI Sync helpers
    # ─────────────────────────────────────────────────────────────────────────
    def _sync_g1_ui(self):
        self.g1_text.delete("1.0", "end")
        lines = []
        for u, v, data in self.g1.G.edges(data=True):
            lines.append(f"{u},{v},{data.get('distance',0)},{data.get('cost',0)}")
        self.g1_text.insert("1.0", "\n".join(lines))
        self.g1_src.delete(0, 'end')
        self.g1_src.insert(0, ",".join(sorted(self.g1.sources)))
        self.g1_sink.delete(0, 'end')
        self.g1_sink.insert(0, ",".join(sorted(self.g1.sinks)))

    def _sync_g2_ui(self):
        self.g2_text.delete("1.0", "end")
        lines = []
        for u, v, data in self.g2.G.edges(data=True):
            lines.append(f"{u},{v},{data.get('distance',0)},{data.get('cost',0)}")
        self.g2_text.insert("1.0", "\n".join(lines))
        self.g2_src.delete(0, 'end')
        self.g2_src.insert(0, ",".join(sorted(self.g2.sources)))
        self.g2_sink.delete(0, 'end')
        self.g2_sink.insert(0, ",".join(sorted(self.g2.sinks)))

    # ─────────────────────────────────────────────────────────────────────────
    # Parsing / Loading
    # ─────────────────────────────────────────────────────────────────────────
    def parse_edges(self, text):
        edges = []
        for line in text.splitlines():
            line = line.strip()
            if not line: continue
            parts = [p.strip() for p in line.split(',')]
            if len(parts) != 4:
                raise ValueError(f"Bad format: {line}")
            u, v, d, c = parts
            edges.append((u.strip(), v.strip(), float(d), float(c)))
        return edges

    def load_g1(self):
        try:
            edges = self.parse_edges(self.g1_text.get("1.0", "end"))
        except Exception as e:
            messagebox.showwarning("Error", str(e)); return
        self._take_snapshot()
        self.g1.clear()
        for u, v, d, c in edges:
            self.g1.add_edge(u, v, d, c, 'g1')
        self.g1.sources = set(s.strip() for s in self.g1_src.get().split(',') if s.strip())
        self.g1.sinks   = set(s.strip() for s in self.g1_sink.get().split(',') if s.strip())
        self._update_info(); self.redraw_all()

    def load_g2(self):
        try:
            edges = self.parse_edges(self.g2_text.get("1.0", "end"))
        except Exception as e:
            messagebox.showwarning("Error", str(e)); return
        self._take_snapshot()
        self.g2.clear()
        for u, v, d, c in edges:
            self.g2.add_edge(u, v, d, c, 'g2')
        self.g2.sources = set(s.strip() for s in self.g2_src.get().split(',') if s.strip())
        self.g2.sinks   = set(s.strip() for s in self.g2_sink.get().split(',') if s.strip())
        self._update_info(); self.redraw_all()

    def add_links(self):
        try:
            edges = self.parse_edges(self.links_text.get("1.0", "end"))
        except Exception as e:
            messagebox.showwarning("Error", str(e)); return
        for u, v, d, c in edges:
            if u not in self.g1.sinks or v not in self.g2.sources:
                messagebox.showwarning("Неможливо додати дугу",
                                       "Неможливо додати дугу — порушується структура.")
                return
        self._take_snapshot()
        for e in edges:
            self.links.append(e)
        self._refresh_links_text(); self._update_info(); self.redraw_all()

    # ── ОНОВЛЕНІ методи завантаження G1/G2 з файлу ───────────────────────────

    def load_g1_file(self):
        path = filedialog.askopenfilename(
            title="Open Graph 1 file",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not path:
            return

        try:
            edges, sources, sinks, _links = parse_graph_file(path)
        except Exception as e:
            messagebox.showwarning("File error", f"Не вдалося прочитати файл:\n{e}")
            return

        if not edges:
            messagebox.showwarning("Порожній файл", "Файл не містить жодної дуги.")
            return

        # Populate edges text field (only edge lines, no section headers)
        edge_lines = "\n".join(f"{u},{v},{d},{c}" for u, v, d, c in edges)
        self.g1_text.delete("1.0", "end")
        self.g1_text.insert("1.0", edge_lines)

        # Auto-fill sources and sinks if present in file
        if sources:
            self.g1_src.delete(0, 'end')
            self.g1_src.insert(0, ",".join(sorted(sources)))

        if sinks:
            self.g1_sink.delete(0, 'end')
            self.g1_sink.insert(0, ",".join(sorted(sinks)))

        # Trigger the normal load
        self.load_g1()

        # Inform user if sources/sinks were auto-populated
        msg_parts = []
        if sources:
            msg_parts.append(f"Sources автоматично заповнено: {', '.join(sorted(sources))}")
        if sinks:
            msg_parts.append(f"Sinks автоматично заповнено: {', '.join(sorted(sinks))}")
        if msg_parts:
            messagebox.showinfo("Graph 1 завантажено", "\n".join(msg_parts))

    def load_g2_file(self):
        path = filedialog.askopenfilename(
            title="Open Graph 2 file",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not path:
            return

        try:
            edges, sources, sinks, _links = parse_graph_file(path)
        except Exception as e:
            messagebox.showwarning("File error", f"Не вдалося прочитати файл:\n{e}")
            return

        if not edges:
            messagebox.showwarning("Порожній файл", "Файл не містить жодної дуги.")
            return

        # Populate edges text field (only edge lines, no section headers)
        edge_lines = "\n".join(f"{u},{v},{d},{c}" for u, v, d, c in edges)
        self.g2_text.delete("1.0", "end")
        self.g2_text.insert("1.0", edge_lines)

        # Auto-fill sources and sinks if present in file
        if sources:
            self.g2_src.delete(0, 'end')
            self.g2_src.insert(0, ",".join(sorted(sources)))

        if sinks:
            self.g2_sink.delete(0, 'end')
            self.g2_sink.insert(0, ",".join(sorted(sinks)))

        # Trigger the normal load
        self.load_g2()

        # Inform user if sources/sinks were auto-populated
        msg_parts = []
        if sources:
            msg_parts.append(f"Sources автоматично заповнено: {', '.join(sorted(sources))}")
        if sinks:
            msg_parts.append(f"Sinks автоматично заповнено: {', '.join(sorted(sinks))}")
        if msg_parts:
            messagebox.showinfo("Graph 2 завантажено", "\n".join(msg_parts))

    # ─────────────────────────────────────────────────────────────────────────

    def load_links_file(self):
        path = filedialog.askopenfilename(title="Open Links file",
                                          filetypes=[("Text files","*.txt"),("All files","*.*")])
        if not path: return
        if not self._read_file_to_textwidget(path, self.links_text): return
        try:
            edges = self.parse_edges(self.links_text.get("1.0", "end"))
        except Exception as e:
            messagebox.showwarning("Error", f"Bad links file format: {e}"); return
        bad = [(u, v) for u, v, d, c in edges
               if u not in self.g1.sinks or v not in self.g2.sources]
        if bad:
            messagebox.showwarning("Неможливо додати дуги",
                                   "Деякі дуги порушують структуру:\n" +
                                   ", ".join(f"{u}->{v}" for u, v in bad))
            return
        self._take_snapshot()
        for e in edges: self.links.append(e)
        self._refresh_links_text(); self._update_info(); self.redraw_all()

    def _read_file_to_textwidget(self, path, widget):
        for enc in ('utf-8', 'utf-8-sig', 'cp1251'):
            try:
                with open(path, 'r', encoding=enc) as f:
                    data = f.read()
                widget.delete("1.0", "end"); widget.insert("1.0", data)
                return True
            except UnicodeDecodeError:
                continue
            except Exception as e:
                messagebox.showwarning("File error", f"Не вдалося відкрити файл: {e}")
                return False
        messagebox.showwarning("File error", "Не вдалося прочитати файл.")
        return False

    def _refresh_links_text(self):
        self.links_text.delete("1.0", "end")
        if self.links:
            self.links_text.insert("1.0",
                "\n".join(f"{u},{v},{d},{c}" for u, v, d, c in self.links))

    # ─────────────────────────────────────────────────────────────────────────
    # Active graph helper
    # ─────────────────────────────────────────────────────────────────────────
    def _get_active_graph_and_sets(self):
        idx = self.notebook.index(self.notebook.select())
        if idx == 0:
            return self.g1.G, self.g1.edge_tag, self.g1.sources, self.g1.sinks, self.canvas1
        elif idx == 1:
            return self.g2.G, self.g2.edge_tag, self.g2.sources, self.g2.sinks, self.canvas2
        else:
            C, tag = build_combined(self.g1, self.g2, self.links)
            return C, tag, self.g1.sources, self.g2.sinks, self.canvas3

    # ─────────────────────────────────────────────────────────────────────────
    # Compute dispatcher
    # ─────────────────────────────────────────────────────────────────────────
    def compute_fast(self):
        if self.algorithm_var.get() == 'ford_fulkerson':
            self.compute_ff_fast()
        else:
            self.compute_sp_fast()

    def compute_step(self):
        if self.algorithm_var.get() == 'ford_fulkerson':
            self.compute_ff_step()
        else:
            self.compute_sp_step()

    # ─────────────────────────────────────────────────────────────────────────
    # Shortest Path: fast
    # ─────────────────────────────────────────────────────────────────────────
    def compute_sp_fast(self):
        G, tag, sources, sinks, canvas = self._get_active_graph_and_sets()
        self._update_info()
        if G is None or len(G.nodes) == 0:
            messagebox.showinfo("Info", "Граф порожній."); return
        if not sources or not sinks:
            messagebox.showinfo("Info", "Не задані джерела або стоки."); return

        per_pair_results = []
        distance_edges_union, cost_edges_union = set(), set()

        t0 = time.perf_counter()
        for s in sorted(sources):
            for t in sorted(sinks):
                if s not in G.nodes() or t not in G.nodes():
                    per_pair_results.append((s, t, None, [], None, [])); continue
                try:
                    dlen  = nx.shortest_path_length(G, source=s, target=t, weight='distance')
                    dpaths = list(nx.all_shortest_paths(G, source=s, target=t, weight='distance'))
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    dlen, dpaths = None, []
                try:
                    clen  = nx.shortest_path_length(G, source=s, target=t, weight='cost')
                    cpaths = list(nx.all_shortest_paths(G, source=s, target=t, weight='cost'))
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    clen, cpaths = None, []
                per_pair_results.append((s, t, dlen, dpaths, clen, cpaths))
                for paths, union in ((dpaths, distance_edges_union), (cpaths, cost_edges_union)):
                    for path in paths:
                        for i in range(len(path) - 1):
                            union.add(frozenset((path[i], path[i + 1])))
        elapsed_sp = time.perf_counter() - t0
        self._sp_elapsed = elapsed_sp

        highlight_map = {'final_best': distance_edges_union, 'final_best_cost': cost_edges_union}
        active_idx    = self.notebook.index(self.notebook.select())
        self.redraw_all(highlight_edges_map=highlight_map, highlight_tab=active_idx)

        lines = ["=== Найкоротші шляхи (швидкий режим) ==="]
        for s, t, dlen, dpaths, clen, cpaths in per_pair_results:
            header = f"{s} -> {t}:"
            if dpaths:
                if len(dpaths) == 1:
                    lines.append(f"{header} by distance: path = {' -> '.join(dpaths[0])}, total = {dlen}")
                else:
                    lines.append(f"{header} by distance: {len(dpaths)} шляхи, total = {dlen}")
                    for i, p in enumerate(dpaths, 1): lines.append(f"{'':6}{i}) {' -> '.join(p)}")
            else:
                lines.append(f"{header} by distance: no path")
            if cpaths:
                if len(cpaths) == 1:
                    lines.append(f"{'':6}by cost: path = {' -> '.join(cpaths[0])}, total = {clen}")
                else:
                    lines.append(f"{'':6}by cost: {len(cpaths)} шляхи, total = {clen}")
                    for i, p in enumerate(cpaths, 1): lines.append(f"{'':6}{i}) {' -> '.join(p)}")
            else:
                lines.append(f"{'':6}by cost: no path")
            lines.append("")
        lines.append(f"Час виконання (НШ): {elapsed_sp * 1000:.4f} мс")
        self.info_box.delete("1.0", "end")
        self.info_box.insert("1.0", "\n".join(lines))
        return elapsed_sp

    # ─────────────────────────────────────────────────────────────────────────
    # Shortest Path: step-by-step
    # ─────────────────────────────────────────────────────────────────────────
    def compute_sp_step(self):
        G, tag, sources, sinks, canvas = self._get_active_graph_and_sets()
        self._update_info()
        if G is None or len(G.nodes) == 0:
            messagebox.showinfo("Info", "Граф порожній."); return
        if not sources or not sinks:
            messagebox.showinfo("Info", "Не задані джерела або стоки."); return

        criterion  = self.criterion_var.get()
        self.steps = []
        for s in sorted(sources):
            for t in sorted(sinks):
                self.steps.append({
                    'desc': f"--- Початок розгляду пари {s} -> {t}, критерій {criterion}. ---",
                    'highlight': {}, 'source_node': s, 'edge_label_override': None})
                self.steps.extend(build_steps_for_pair(G, s, t, weight_attr=criterion))
                self.steps.append({
                    'desc': f"--- Кінець розгляду пари {s} -> {t} ---",
                    'highlight': {}, 'source_node': None, 'edge_label_override': None})

        self.step_index = -1
        self.step_forward()

    # ─────────────────────────────────────────────────────────────────────────
    # Ford-Fulkerson: fast
    # ─────────────────────────────────────────────────────────────────────────
    def compute_ff_fast(self):
        G, tag, sources, sinks, canvas = self._get_active_graph_and_sets()
        self._update_info()
        if G is None or len(G.nodes) == 0:
            messagebox.showinfo("Info", "Граф порожній."); return
        if not sources or not sinks:
            messagebox.showinfo("Info", "Не задані джерела або стоки."); return

        criterion  = self.criterion_var.get()
        attr_label = 'відстань' if criterion == 'distance' else 'вартість'

        original_cap = {}
        for u, v, data in G.edges(data=True):
            original_cap[frozenset((u, v))] = float(data.get(criterion, 1.0))

        agg_flow = {}
        for u, v in G.edges():
            agg_flow[(u, v)] = 0.0
            agg_flow[(v, u)] = 0.0

        results        = []
        all_used_union = set()

        t0 = time.perf_counter()
        for s in sorted(sources):
            for t in sorted(sinks):
                if s not in G.nodes() or t not in G.nodes():
                    results.append((s, t, None, set())); continue
                flow, used, df = run_ff_compute(G, s, t, weight_attr=criterion)
                results.append((s, t, flow, used))
                all_used_union.update(used)
                for arc, val in df.items():
                    agg_flow[arc] = agg_flow.get(arc, 0.0) + val
        elapsed_ff = time.perf_counter() - t0
        self._ff_elapsed = elapsed_ff

        edge_label_override = {}
        for u, v in G.edges():
            key  = frozenset((u, v))
            cap  = original_cap.get(key, 1.0)
            net  = agg_flow.get((u, v), 0.0) - agg_flow.get((v, u), 0.0)
            used_val  = abs(net)
            remaining = max(0.0, cap - used_val)
            edge_label_override[key] = f"{remaining:.0f}/{used_val:.0f}"

        highlight_map = {'final': all_used_union} if all_used_union else {}
        active_idx    = self.notebook.index(self.notebook.select())
        self.redraw_all(highlight_edges_map=highlight_map, highlight_tab=active_idx,
                        edge_label_override=edge_label_override)

        lines = [f"=== Форд-Фалкерсон (швидкий режим, критерій: {attr_label}) ===", ""]
        for s, t, flow, _ in results:
            if flow is not None:
                lines.append(f"  {s} -> {t}: максимальний потік = {flow:.0f}")
            else:
                lines.append(f"  {s} -> {t}: шлях не знайдено")
        lines.append("")
        lines.append(f"Час виконання (ФФ): {elapsed_ff * 1000:.4f} мс")
        self.info_box.delete("1.0", "end")
        self.info_box.insert("1.0", "\n".join(lines))
        return elapsed_ff

    # ─────────────────────────────────────────────────────────────────────────
    # Speed comparison
    # ─────────────────────────────────────────────────────────────────────────
    def compare_speed(self):
        missing = []
        if self._sp_elapsed is None: missing.append("НШ")
        if self._ff_elapsed is None: missing.append("ФФ")
        if missing:
            messagebox.showinfo("Порівняння недоступне",
                                f"Спочатку запустіть Compute (fast) для: {', '.join(missing)}.")
            return

        sp_t = self._sp_elapsed
        ff_t = self._ff_elapsed

        if sp_t < ff_t:
            ratio   = ff_t / sp_t if sp_t > 0 else float('inf')
            verdict = f"НШ швидший за ФФ у {ratio:.2f}x"
            bar_sp  = "=" * 10
            bar_ff  = "=" * min(50, round(10 * ratio))
        elif ff_t < sp_t:
            ratio   = sp_t / ff_t if ff_t > 0 else float('inf')
            verdict = f"ФФ швидший за НШ у {ratio:.2f}x"
            bar_ff  = "=" * 10
            bar_sp  = "=" * min(50, round(10 * ratio))
        else:
            ratio   = 1.0
            verdict = "Алгоритми однакові за швидкістю"
            bar_sp  = bar_ff = "=" * 10

        lines = [
            "=== Порівняння швидкості (останній Compute fast) ===", "",
            f"  SP: {sp_t * 1000:.4f} мс",
            f"  SP [{bar_sp}]", "",
            f"  FF: {ff_t * 1000:.4f} мс",
            f"  FF [{bar_ff}]", "",
            f"  -> {verdict}",
        ]
        self.info_box.delete("1.0", "end")
        self.info_box.insert("1.0", "\n".join(lines))

    # ─────────────────────────────────────────────────────────────────────────
    # Ford-Fulkerson: step-by-step
    # ─────────────────────────────────────────────────────────────────────────
    def compute_ff_step(self):
        G, tag, sources, sinks, canvas = self._get_active_graph_and_sets()
        self._update_info()
        if G is None or len(G.nodes) == 0:
            messagebox.showinfo("Info", "Граф порожній."); return
        if not sources or not sinks:
            messagebox.showinfo("Info", "Не задані джерела або стоки."); return

        criterion  = self.criterion_var.get()
        attr_label = 'відстань' if criterion == 'distance' else 'вартість'
        self.steps = []

        for s in sorted(sources):
            for t in sorted(sinks):
                self.steps.append({
                    'desc': (f"--- Форд-Фалкерсон: пара {s} -> {t}, "
                             f"критерій «{attr_label}». ---"),
                    'highlight': {}, 'source_node': s, 'edge_label_override': None})
                pair_steps, total_flow = build_ff_steps(G, s, t, weight_attr=criterion)
                self.steps.extend(pair_steps)
                self.steps.append({
                    'desc': (f"--- Кінець ФФ для пари {s} -> {t}. "
                             f"Максимальний потік: {total_flow:.0f} ---"),
                    'highlight': {}, 'source_node': None, 'edge_label_override': None})

        self.step_index = -1
        self.step_forward()

    # ─────────────────────────────────────────────────────────────────────────
    # Step navigation
    # ─────────────────────────────────────────────────────────────────────────
    def step_forward(self):
        if not self.steps:
            messagebox.showinfo("Info", "Немає кроків. Запустіть покроковий режим."); return
        if self.step_index < len(self.steps) - 1:
            self.step_index += 1; self._apply_step()

    def step_back(self):
        if not self.steps: return
        if self.step_index > 0:
            self.step_index -= 1; self._apply_step()

    def _apply_step(self):
        step = self.steps[self.step_index]
        self.info_box.delete("1.0", "end")
        self.info_box.insert("1.0", step['desc'])
        self.step_label.config(text=f"Крок: {self.step_index + 1} / {len(self.steps)}")

        active_idx          = self.notebook.index(self.notebook.select())
        source_node         = step.get('source_node', None)
        edge_label_override = step.get('edge_label_override', None)

        hm = {}
        for k, s in step.get('highlight', {}).items():
            hm[k] = set()
            for e in s:
                if isinstance(e, frozenset):
                    lst = list(e)
                    if len(lst) == 2:   hm[k].add((lst[0], lst[1]))
                    elif len(lst) == 1: hm[k].add((lst[0], lst[0]))
                elif isinstance(e, (tuple, list)) and len(e) == 2:
                    hm[k].add(tuple(e))

        self.redraw_all(highlight_edges_map=hm, highlight_tab=active_idx,
                        source_node=source_node, edge_label_override=edge_label_override)

    # ─────────────────────────────────────────────────────────────────────────
    # Redraw
    # ─────────────────────────────────────────────────────────────────────────
    def redraw_all(self, highlight_edges_map=None, highlight_tab=None,
                   source_node=None, edge_label_override=None):
        elo1 = edge_label_override if highlight_tab == 0 else None
        elo2 = edge_label_override if highlight_tab == 1 else None
        elo3 = edge_label_override if highlight_tab == 2 else None

        node_colors1 = {n: '#aaaaaa' for n in self.g1.G.nodes()
                        if n in self.g1.sources or n in self.g1.sinks}
        pos1 = getattr(self.canvas1, 'pos', {}) or {}
        self.canvas1.draw(self.g1.G, self.g1.edge_tag, node_colors=node_colors1,
                          highlight_edges_map=highlight_edges_map if highlight_tab == 0 else None,
                          external_pos=pos1,
                          source_node=source_node if highlight_tab == 0 else None,
                          edge_label_override=elo1)

        node_colors2 = {n: '#aaaaaa' for n in self.g2.G.nodes()
                        if n in self.g2.sources or n in self.g2.sinks}
        pos2 = getattr(self.canvas2, 'pos', {}) or {}
        self.canvas2.draw(self.g2.G, self.g2.edge_tag, node_colors=node_colors2,
                          highlight_edges_map=highlight_edges_map if highlight_tab == 1 else None,
                          external_pos=pos2,
                          source_node=source_node if highlight_tab == 1 else None,
                          edge_label_override=elo2)

        C, tag = build_combined(self.g1, self.g2, self.links)
        node_colors3 = {n: '#aaaaaa' for n in C.nodes()
                        if n in self.g1.sources or n in self.g2.sinks}
        merged_pos = {}
        for n in C.nodes():
            if n in pos1:   merged_pos[n] = pos1[n]
            elif n in pos2: merged_pos[n] = pos2[n]
        self.canvas3.draw(C, tag, node_colors=node_colors3,
                          highlight_edges_map=highlight_edges_map if highlight_tab == 2 else None,
                          external_pos=merged_pos,
                          source_node=source_node if highlight_tab == 2 else None,
                          edge_label_override=elo3)
        self.combined_graph = C; self.combined_tag = tag

    def _update_info(self):
        lines = [
            "Graph 1:",
            f"  Nodes: {len(self.g1.G.nodes())}",
            f"  Edges: {len(self.g1.G.edges())}",
            f"  Sources: {', '.join(sorted(self.g1.sources)) or 'None'}",
            f"  Sinks:   {', '.join(sorted(self.g1.sinks))   or 'None'}",
            "",
            "Graph 2:",
            f"  Nodes: {len(self.g2.G.nodes())}",
            f"  Edges: {len(self.g2.G.edges())}",
            f"  Sources: {', '.join(sorted(self.g2.sources)) or 'None'}",
            f"  Sinks:   {', '.join(sorted(self.g2.sinks))   or 'None'}",
            "",
            "Links G1 -> G2:",
            f"  Count: {len(self.links)}",
        ]
        if self.links:
            lines.append("  " + ", ".join(
                f"{u}->{v}(d={d},c={c})" for u, v, d, c in self.links))
        self.info_box.delete("1.0", "end")
        self.info_box.insert("1.0", "\n".join(lines))


if __name__ == "__main__":
    app = App()
    app.mainloop()
