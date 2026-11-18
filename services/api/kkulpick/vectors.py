"""Trusted worker/owner helpers. Inputs must be public catalog text embeddings, never personal OCR."""
import math
from dataclasses import asdict, dataclass
from psycopg import sql

TARGETS = {"product":("products","catalog_items","item_id"),"food":("foods","catalog_items","item_id"),
           "ingredient":("ingredients","ingredients","ingredient_id")}


@dataclass(frozen=True)
class Contract:
    model_id: str
    target: str
    encoder_name: str
    revision: str
    dimensions: int
    input_template: str
    query_prefix: str
    document_prefix: str
    normalize: bool


def register(conn, contract):
    """Owner connection; transaction includes immutable contract and its matching partial HNSW index."""
    k = contract
    if k.target not in TARGETS or not 1 <= k.dimensions <= 2000 or not all(
        x.strip() for x in (k.model_id,k.encoder_name,k.revision,k.input_template)):
        raise ValueError("invalid model contract")
    values=asdict(k)
    with conn.transaction():
        conn.execute("""INSERT INTO app.embedding_models(model_id,target,encoder_name,revision,dimensions,input_template,
          query_prefix,document_prefix,normalize) VALUES (%(model_id)s,%(target)s,%(encoder_name)s,%(revision)s,
          %(dimensions)s,%(input_template)s,%(query_prefix)s,%(document_prefix)s,%(normalize)s)""",values)
        # PostgreSQL chooses an index name unique within the schema.
        conn.execute(sql.SQL("CREATE INDEX ON app.{} USING hnsw ((embedding::vector({})) vector_cosine_ops) "
                             "WITH(m=16,ef_construction=64) WHERE model_id={}").format(
                             sql.Identifier(k.target+"_embeddings"),sql.Literal(k.dimensions),sql.Literal(k.model_id)))


def _space(conn, model, values):
    r=conn.execute("SELECT target,dimensions FROM app.embedding_models WHERE model_id=%s AND is_serving",(model,)).fetchone()
    if not r:
        raise ValueError("no serving model with this id")
    target,dim=r
    if len(values)!=dim or not all(math.isfinite(v) for v in values) or not any(values):
        raise ValueError("non-finite/zero vector or dimension mismatch")
    return target,dim,"["+ ",".join(str(float(v)) for v in values)+"]"


def put(conn, model, parent_id, version, values):
    with conn.transaction():
        t,_,vec=_space(conn,model,values)
        col=sql.Identifier(t+"_id")
        conn.execute(sql.SQL("INSERT INTO app.{} ({},model_id,content_version,embedding) VALUES (%s,%s,%s,%s::vector) "
            "ON CONFLICT ({},model_id) DO UPDATE SET content_version=excluded.content_version, "
            "embedding=excluded.embedding,created_at=now()").format(sql.Identifier(t+"_embeddings"),col,col),
            (parent_id,model,version,vec))


def candidates(conn, model, values, limit=20):
    """Returns candidate identities, not a price, an allergy verdict or a final recommendation."""
    if not 1<=limit<=100:
        raise ValueError("invalid limit")
    with conn.transaction():
        t,dim,vec=_space(conn,model,values)
        _,parent,pk=TARGETS[t]
        conn.execute("SET LOCAL hnsw.ef_search=40")
        conn.execute("SET LOCAL hnsw.iterative_scan=strict_order")
        distance=sql.SQL("e.embedding::vector({}) <=> %s::vector({})").format(sql.Literal(dim),sql.Literal(dim))
        stmt=sql.SQL("SELECT e.{},{} AS distance FROM app.{} e JOIN app.{} p ON e.{}=p.{} "
                     "AND e.content_version=p.content_version WHERE e.model_id={} ORDER BY distance LIMIT %s").format(
                     sql.Identifier(t+"_id"),distance,sql.Identifier(t+"_embeddings"),sql.Identifier(parent),
                     sql.Identifier(t+"_id"),sql.Identifier(pk),sql.Literal(model))
        rows=conn.execute(stmt,(vec,limit)).fetchall()
        if len(rows)<limit:
            # Exact fallback for stale/filtered candidates on sparse domains.
            exact=sql.SQL("SELECT * FROM ({}) q ORDER BY distance LIMIT %s").format(
                sql.SQL("SELECT e.{},{} AS distance FROM app.{} e JOIN app.{} p ON e.{}=p.{} AND "
                        "e.content_version=p.content_version WHERE e.model_id={} OFFSET 0").format(
                    sql.Identifier(t+"_id"),distance,sql.Identifier(t+"_embeddings"),sql.Identifier(parent),
                    sql.Identifier(t+"_id"),sql.Identifier(pk),sql.Literal(model)))
            rows=conn.execute(exact,(vec,limit)).fetchall()
        return rows
