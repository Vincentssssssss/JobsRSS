# Job Sources

## Phase 1

### Company Career Sites

1. Alibaba
2. Microsoft
3. Huawei

### Chinese Platforms

4. 51job
5. Liepin

### International

6. LinkedIn Job Alerts via Email

---

# Collector Requirements

Each collector must expose:

- source name
- source type
- collection method
- search configuration
- polling interval
- parser
- normalization logic

---

# Important

Before implementing a collector:

1. Inspect the actual website.
2. Determine whether an API exists.
3. Determine whether structured JSON exists.
4. Determine whether RSS exists.
5. Determine whether sitemap exists.
6. Only then use HTML/browser automation.

Do not assume the website implementation.

The collector should document:

- URL
- data source
- extraction method
- fields extracted
- known limitations
