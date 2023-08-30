pragma solidity >=0.8.6;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "./SearcherBase.sol";

contract SimpleSearcher is Ownable, SearcherBase {
    IERC20 public immutable weth;

    constructor(
        address _trustedSearcherCapsule,
        address _trustedSearcherRequestCall,
        IERC20 _wethAddress
    ) SearcherBase(_trustedSearcherCapsule, _trustedSearcherRequestCall) {
        weth = _wethAddress;
    }

    function execute(uint256 bid) external onlyTrustedRequestCall {
        (bool sent, ) = address(weth).call{value: bid}("");
        require(sent, "Failed to wrap token");
        weth.transfer(trustedExecutionCapsule, bid);
    }

    receive() external payable {}
}
