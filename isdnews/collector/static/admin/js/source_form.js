function handleTypeChange(selectElement) {
    var paramsField = document.getElementById('id_params');
    if (selectElement.value === 'static') {
        var defaultParams = {
            "prompt": "hãy lấy các url liên quan đến [nội dung bạn cần lấy] sau đó gửi lại cho tôi , yêu cầu dữ liệu trả về chỉ là 1 mảng các url, không được sai format như tôi yêu cầu"
        };
        paramsField.value = JSON.stringify(defaultParams, null, 2);
    }
}
