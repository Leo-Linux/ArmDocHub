#!/usr/bin/env bash
# fetch-arm-docs.sh
# 批量下载 ARM 官方文档,按物理路径归档。
#
# 用法:
#   ./fetch-arm-docs.sh [输出根目录]
#   默认 ./arm-docs
#
# TSV 字段:category, id, doc_id, title, url, type, views, role, note
# 详见 docs.tsv 顶部注释。

set -u

ROOT="${1:-./arm-docs}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TSV="$SCRIPT_DIR/docs.tsv"

if [[ ! -f "$TSV" ]]; then
    echo "ERROR: docs.tsv not found at $TSV" >&2
    exit 1
fi

mkdir -p "$ROOT"
MANIFEST="$ROOT/manifest.csv"
MISSING="$ROOT/MISSING.md"
LOGFILE="$ROOT/download.log"

if [[ ! -f "$MANIFEST" ]]; then
    echo "category,id,doc_id,title,url,type,views,role,status,bytes,sha256,fetched_at" > "$MANIFEST"
fi

{
    echo "# 需要手动下载的文档"
    echo ""
    echo "以下文档只有 HTML 详情页可以脚本抓取。真 PDF 需要你手动到 URL"
    echo "点 \"Download PDF\"(部分需 Arm 账号登录)。"
    echo ""
    echo "下完后请放到对应分类目录下,文件名建议保持 \`<id>.pdf\`。"
    echo ""
} > "$MISSING"

UA="Mozilla/5.0 (compatible; arm-doc-fetcher/2.0; reference-collector)"
TIMEOUT=120
RETRIES=3

log() {
    local msg="[$(date '+%H:%M:%S')] $*"
    echo "$msg"
    echo "$msg" >> "$LOGFILE"
}

fetch_one() {
    local url="$1" outfile="$2"
    curl --fail --silent --show-error --location \
         --user-agent "$UA" \
         --connect-timeout 15 --max-time "$TIMEOUT" \
         --retry "$RETRIES" --retry-delay 3 --retry-all-errors \
         -C - \
         -o "$outfile" \
         "$url"
}

sha256_of() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    else
        echo "no-sha-tool"
    fi
}

file_size() {
    stat -f%z "$1" 2>/dev/null || stat -c%s "$1"
}

csv_escape() {
    local s="$1"
    if [[ "$s" == *,* || "$s" == *\"* ]]; then
        s="${s//\"/\"\"}"
        printf '"%s"' "$s"
    else
        printf '%s' "$s"
    fi
}

total=0; ok=0; skip=0; fail=0; missing=0

# 读取 TSV,跳过注释和空行
while IFS=$'\t' read -r category id doc_id title url type views role note; do
    [[ -z "${category:-}" || "$category" =~ ^# ]] && continue
    total=$((total+1))

    catdir="$ROOT/$category"
    mkdir -p "$catdir"

    case "$type" in
        pdf)
            outfile="$catdir/${id}.pdf"
            if [[ -s "$outfile" ]]; then
                size=$(file_size "$outfile")
                hash=$(sha256_of "$outfile")
                log "SKIP  [$category] $id ($size bytes)"
                printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
                    "$(csv_escape "$category")" \
                    "$(csv_escape "$id")" \
                    "$(csv_escape "$doc_id")" \
                    "$(csv_escape "$title")" \
                    "$(csv_escape "$url")" \
                    "$type" \
                    "$(csv_escape "$views")" \
                    "$(csv_escape "$role")" \
                    "skipped" "$size" "$hash" "$(date -u +%FT%TZ)" >> "$MANIFEST"
                skip=$((skip+1))
                continue
            fi
            log "GET   [$category] $id <- $url"
            if fetch_one "$url" "$outfile.part"; then
                mv "$outfile.part" "$outfile"
                size=$(file_size "$outfile")
                hash=$(sha256_of "$outfile")
                if head -c 4 "$outfile" | grep -q '%PDF'; then
                    log "OK    $id ($size bytes)"
                    status="ok"
                    ok=$((ok+1))
                else
                    log "WARN  $id 下载成功但不是 PDF,可能是错误页"
                    mv "$outfile" "$outfile.not-pdf.html"
                    status="not-pdf"
                    fail=$((fail+1))
                fi
                printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
                    "$(csv_escape "$category")" \
                    "$(csv_escape "$id")" \
                    "$(csv_escape "$doc_id")" \
                    "$(csv_escape "$title")" \
                    "$(csv_escape "$url")" \
                    "$type" \
                    "$(csv_escape "$views")" \
                    "$(csv_escape "$role")" \
                    "$status" "$size" "$hash" "$(date -u +%FT%TZ)" >> "$MANIFEST"
            else
                rc=$?
                rm -f "$outfile.part"
                log "FAIL  $id curl exit=$rc"
                printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
                    "$(csv_escape "$category")" \
                    "$(csv_escape "$id")" \
                    "$(csv_escape "$doc_id")" \
                    "$(csv_escape "$title")" \
                    "$(csv_escape "$url")" \
                    "$type" \
                    "$(csv_escape "$views")" \
                    "$(csv_escape "$role")" \
                    "failed" "0" "" "$(date -u +%FT%TZ)" >> "$MANIFEST"
                fail=$((fail+1))
            fi
            ;;
        html)
            outfile="$catdir/${id}.detail.html"
            if [[ ! -s "$outfile" ]]; then
                log "GET   [$category] $id (detail) <- $url"
                if fetch_one "$url" "$outfile.part"; then
                    mv "$outfile.part" "$outfile"
                    size=$(file_size "$outfile")
                    hash=$(sha256_of "$outfile")
                    log "OK    $id detail saved ($size bytes)"
                    status="detail-only"
                else
                    rm -f "$outfile.part"
                    size=0; hash=""
                    log "FAIL  $id detail fetch failed"
                    status="failed"
                fi
            else
                size=$(file_size "$outfile")
                hash=$(sha256_of "$outfile")
                log "SKIP  [$category] $id (detail already saved)"
                status="detail-only"
                skip=$((skip+1))
            fi

            printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
                "$(csv_escape "$category")" \
                "$(csv_escape "$id")" \
                "$(csv_escape "$doc_id")" \
                "$(csv_escape "$title")" \
                "$(csv_escape "$url")" \
                "$type" \
                "$(csv_escape "$views")" \
                "$(csv_escape "$role")" \
                "$status" "$size" "$hash" "$(date -u +%FT%TZ)" >> "$MANIFEST"

            echo "## [$category] $title" >> "$MISSING"
            echo "" >> "$MISSING"
            echo "- ID: \`$id\`(${doc_id})" >> "$MISSING"
            echo "- 视图: ${views:--}" >> "$MISSING"
            echo "- 角色: ${role:--}" >> "$MISSING"
            echo "- 详情页: <$url>" >> "$MISSING"
            echo "- 建议保存为: \`$category/${id}.pdf\`" >> "$MISSING"
            echo "" >> "$MISSING"
            missing=$((missing+1))
            ;;
        *)
            log "ERROR unknown type=$type for $id"
            ;;
    esac
done < "$TSV"

# 生成 README
{
    echo "# ARM 官方文档归档"
    echo ""
    echo "为《系统虚拟化原理与实现》服务的参考资料库。"
    echo "生成时间: $(date '+%F %T %Z')"
    echo ""
    echo "## 统计"
    echo ""
    echo "- 总条目: $total"
    echo "- 直链 PDF 成功: $ok"
    echo "- 已存在跳过: $skip"
    echo "- 失败: $fail"
    echo "- 仅 HTML 详情(需手动): $missing"
    echo ""
    echo "## 物理路径结构(六大类、18 子类)"
    echo ""
    echo "\`\`\`"
    if command -v tree >/dev/null 2>&1; then
        (cd "$ROOT" && tree -L 2 --noreport -I '*.html|*.log|*.csv|*.md')
    else
        (cd "$ROOT" && find . -maxdepth 2 -type d ! -name 'views' | sort | sed 's|^\./||')
    fi
    echo "\`\`\`"
    echo ""
    echo "## 重要文件"
    echo ""
    echo "- [manifest.csv](./manifest.csv) — 全量记录"
    echo "- [MISSING.md](./MISSING.md) — 需手动下的清单"
    echo "- views/ — 虚拟化视图(由 build-views.sh 生成)"
} > "$ROOT/README.md"

log ""
log "============ 完成 ============"
log "总数:$total  成功:$ok  跳过:$skip  失败:$fail  待手动:$missing"
log "输出目录: $ROOT"
